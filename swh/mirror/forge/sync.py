# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import json
import sys
import requests

from os.path import basename

from swh.core.config import SWHConfig
from .api import RepositorySearch, PassphraseSearch, DiffusionUriEdit


FORGE_API_URL = 'https://forge.softwareheritage.org'


class SWHMirrorForge(SWHConfig):
    CONFIG_BASE_FILENAME = 'mirror-forge/config'

    DEFAULT_CONFIG = {
        'github': ('str', None),
        'forge': ('str', None),
    }

    def __init__(self):
        super().__init__()
        self.config = self.parse_config_file()
        self.token_github = self.config['github']
        self.token_forge = self.config['forge']


def prepare_token():
    """Prepare the needed token from the disk.

    Returns:
        tuple (token-forge, token-github)

    """
    swh_mirror_forge = SWHMirrorForge()

    token_forge = swh_mirror_forge.token_forge
    if not token_forge:
        raise ValueError("""Install the phabricator forge's token in
$SWH_CONFIG_PATH/mirror-forge/config.yml
(https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/).

Once the installation is done, you can trigger this script again.""")

    token_github = swh_mirror_forge.token_github
    if not token_github:
        raise ValueError("""Install one personal github token in
$SWH_CONFIG_PATH/mirror-forge/config.yml with scope public_repo
(https://github.com/settings/tokens).

You must be associated to https://github.com/softwareheritage
organization.  Once the installation is done, you can trigger this
script again.""")

    return token_forge, token_github


def mirror_exists(data):
    """Check the existence of the mirror.

    Args:
        data: full information on the repository

    Returns
        True if mirror already exists. False otherwise.

    """
    uris = data['attachments']['uris']['uris']
    for uri in uris:
        effective_url = uri['fields']['uri']['effective']
        if 'github' in effective_url:
            return True

    return False


def retrieve_repo_information(data):
    """Given information on repository, extract the needed information for
       mirroring.

    Args:
        data: full information on the repository

    Returns:
        dict with keys phid, description, url, name.

    """
    uris = data['attachments']['uris']['uris']
    for uri in uris:
        effective_url = uri['fields']['uri']['effective']
        if 'https' in effective_url and '.git' in effective_url:
            elected_url = effective_url

    return {
        'phid': data['phid'],
        'description': data['fields']['name'],
        'url': elected_url,
        'name': basename(elected_url).split('.')[0],
    }


def mirror_repo_to_github(repo_callsign, credential_key_id,
                          token_forge, token_github, dry_run=False):
    """Instantiate a mirror from a repository forge to github if it does
    not already exist.

    Args:
        repo_callsign: repository's identifier callsign. This will be
                       used to fetch information on the repository to
                       mirror.

        credential_key_id: the key the forge will use to push to
                           modifications to github

        token_forge: api token to access the forge's conduit api

        token_github: api token to access github's api.

        dry_run: if True, inhibit the mirror creation (no write is
                done to either github) or the forge.  Otherwise, the
                default, it creates the mirror to github. Also, a
                check is done to stop if a mirror uri is already
                referenced in the forge about github.

    Returns:
        the repository instance whose mirror has been successfully mirrored.
        None if the mirror already exists.

    Raises:
        ValueError if some error occurred during any creation/reading step.
        The detail of the error is in the message.

    """
    # Retrieve repository information
    query = RepositorySearch(FORGE_API_URL, token_forge)
    data = query.request(constraints={
        "callsigns": [repo_callsign],
    }, attachments={
        "uris": True
    })

    repository_information = data[0]

    # Check existence of mirror already set
    if mirror_exists(repository_information):
        return None

    # Retrieve exhaustive information on repository
    repo = retrieve_repo_information(repository_information)
    if not repo:
        raise ValueError('Error when trying to retrieve detailed information'
                         ' on the repository')

    # Create repository in github
    if not dry_run:
        r = requests.post(
            'https://api.github.com/orgs/SoftwareHeritage/repos',
            headers={'Authorization': 'token %s' % token_github},
            data=json.dumps({
                "name": repo['name'],
                "description": repo['description'],
                "homepage": repo['url'],
                "private": False,
                "has_issues": False,
                "has_wiki": False,
                "has_downloads": True
            }))

        if not r.ok:
            raise ValueError("""Failure to create the repository in github.
Status: %s""" % r.status_code)

    # Retrieve credential information

    query = PassphraseSearch(FORGE_API_URL, token_forge)
    data = query.request(ids=[credential_key_id])

    # Retrieve the phid for that passphrase
    key_phid = list(data.values())[0]['phid']

    repo['url_github'] = 'git@github.com:SoftwareHeritage/%s.git' % (
                         repo['name'])

    # Install the github mirror in the forge
    if not dry_run:
        query = DiffusionUriEdit(FORGE_API_URL, token_forge)
        query.request(transactions=[
            {"type": "repository", "value": repo['phid']},
            {"type": "uri", "value": repo['url_github']},
            {"type": "io", "value": "mirror"},
            {"type": "display", "value": "never"},
            {"type": "disable", "value": False},
            {"type": "credential", "value": key_phid},
        ])

    return repo


@click.group()
def cli(): pass


@cli.command()
@click.option('--repo-callsign',
              help="Repository's callsign")
@click.option('--credential-key-id',
              help="""credential to use for access from phabricator's forge to
                      github""")
@click.option('--dry-run/--no-dry-run', default=False)
def mirror(repo_callsign, credential_key_id, dry_run):
    """Shell interface to instantiate a mirror from a repository forge to
    github. Does nothing if the repository already exists.

    Args:
        repo_callsign: repository's identifier callsign. This will be
                       used to fetch information on the repository to
                       mirror.

        credential_key_id: the key the forge will use to push to
                           modifications to github

        dry_run: if True, inhibit the mirror creation (no write is
                done to either github) or the forge.  Otherwise, the
                default, it creates the mirror to github. Also, a
                check is done to stop if a mirror uri is already
                referenced in the forge about github.

    """
    token_forge, token_github = prepare_token()

    msg = ''
    try:
        if dry_run:
            print('** DRY RUN **')

        repo = mirror_repo_to_github(
            repo_callsign, credential_key_id,
            token_forge=token_forge,
            token_github=token_github,
            dry_run=dry_run)

        if repo:
            msg = "Repository %s mirrored at %s." % (
                repo['url'], repo['url_github'])
        else:
            msg = 'Mirror already configured for %s, stopping.' % repo_callsign
    except Exception as e:
        print(e)
        sys.exit(1)
    else:
        print(msg)
        sys.exit(0)


class RepositoriesToMirror(RepositorySearch):
    """Specific query to repository search api to yield callsigns of repository to mirror.

    """
    def parse_response(self, data):
        data = super().parse_response(data)
        for entry in data:
            fields = entry['fields']
            if 'callsign' in fields:
                yield fields['callsign']


def mirror_repos_to_github(query_name, credential_key_id,
                           token_forge, token_github, dry_run):
    """Mirror repositories to github.

    Args:
        credential_key_id: the key the forge will use to push to
                           modifications to github

        query_name: Query's name as per your phabricator forge's
                    setup.

        token_forge: api token to access the forge's conduit api

        token_github: api token to access github's api.

        dry_run: if True, inhibit the mirror creation (no write is
                done to either github) or the forge.  Otherwise, the
                default, it creates the mirror to github. Also, a
                check is done to stop if a mirror uri is already
                referenced in the forge about github.

    Returns:
        dict with keys 'mirrored', 'skipped' and 'errors' keys.

    """
    query = RepositoriesToMirror(FORGE_API_URL, token_forge)
    # query_name = 'sync-to-github-repositories'
    repositories = list(query.request(queryKey=[query_name]))

    if not repositories:
        return None

    errors = []
    mirrored = []
    skipped = []
    for repo_callsign in repositories:
        print(repo_callsign)
        try:
            if dry_run:
                print('** DRY RUN **')

            repo = mirror_repo_to_github(
                repo_callsign, credential_key_id,
                token_forge, token_github, dry_run)

            if repo:
                msg = "Repository %s mirrored at %s." % (
                    repo['url'], repo['url_github'])
                mirrored.append(msg)
            else:
                msg = 'Mirror already configured for %s, stopping.' % repo_callsign
                skipped.append(msg)
            print(msg)
        except Exception as e:
            errors.append(e)
            print(e)

    return {
        'mirrored': mirrored,
        'skipped': skipped,
        'errors': errors
    }


@cli.command()
@click.option('--query-repositories',
              help="""Name of the query that lists the repositories to mirror
                      in github.""")
@click.option('--credential-key-id',
              help="""credential to use for access from phabricator's forge to
                      github""")
@click.option('--dry-run/--no-dry-run', default=False)
def mirrors(query_repositories, credential_key_id, dry_run):
    """Shell interface to instantiate mirrors from a repository forge to
    github. This uses the query_name provided to execute said query.
    The resulting repositories is then mirrored to github if not
    already mirrored.

    Args:
        credential_key_id: the key the forge will use to push to
                           modifications to github

        query_repositories: Query's name which lists the repositories to mirror (as per your phabricator forge's
                            setup).

        dry_run: if True, inhibit the mirror creation (no write is
                done to either github) or the forge.  Otherwise, the
                default, it creates the mirror to github. Also, a
                check is done to stop if a mirror uri is already
                referenced in the forge about github.

    """
    token_forge, token_github = prepare_token()

    if dry_run:
        print('** DRY RUN **')

    r = mirror_repos_to_github(query_name=query_repositories,
                               credential_key_id=credential_key_id,
                               token_forge=token_forge,
                               token_github=token_github,
                               dry_run=dry_run)

    print(r)


if __name__ == '__main__':
    cli()
