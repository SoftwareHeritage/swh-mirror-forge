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
    uris = [u for u in data['attachments']['uris']['uris']
            if not u['fields']['disabled']]
    elected_url = None

    # Will try to retrieve the most relevant uri (https first)
    for uri in uris:
        if uri['fields']['builtin']['protocol'] != 'https':
            continue

        effective_url = uri['fields']['uri']['effective']
        if effective_url.endswith('.git'):
            elected_url = effective_url
            break

    # then fallback to any other if no https were found
    if not elected_url:
        for uri in uris:
            effective_url = uri['fields']['uri']['effective']
            if effective_url.endswith('.git'):
                elected_url = effective_url
                break

    return {
        'phid': data['phid'],
        'description': data['fields']['name'],
        'url': elected_url,
        'name': basename(elected_url).split('.')[0],
    }


class RepositoriesToMirror(RepositorySearch):
    """Specific query to repository search api to yield callsigns of repository
    to mirror.

    """
    def parse_response(self, data):
        data = super().parse_response(data)
        for entry in data:
            fields = entry['fields']
            if 'id' in entry:
                yield entry['id']
            elif 'phid' in entry:
                yield entry['phid']
            elif 'callsign' in fields:
                yield fields['callsign']


class SWHMirrorForge(SWHConfig):
    """Class in charge of mirroring a forge to github.

    """
    CONFIG_BASE_FILENAME = 'mirror-forge/config'

    DEFAULT_CONFIG = {
        'forge_url': ('str', 'https://forge.softwareheritage.org'),
        'tokens': ('dict', {'github': None, 'forge': None})
    }

    def __init__(self):
        super().__init__()
        self.config = self.parse_config_file()
        self.forge_url = self.config['forge_url']
        self.token_github = self.config['tokens']['github']
        self.token_forge = self.config['tokens']['forge']
        self._check()

    def _check(self):
        """Prepare the needed token from the disk.

        Returns:
            tuple (token-forge, token-github)

        """
        if not self.token_forge:
            raise ValueError("""Install the phabricator forge's token in
    $SWH_CONFIG_PATH/mirror-forge/config.yml
    (https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/).

    Once the installation is done, you can trigger this script again.""")

        if not self.token_github:
            raise ValueError("""Install one personal github token in
    $SWH_CONFIG_PATH/mirror-forge/config.yml with scope public_repo
    (https://github.com/settings/tokens).

    You must be associated to https://github.com/softwareheritage
    organization.  Once the installation is done, you can trigger this
    script again.""")

    def mirror_repo_to_github(self, repo_id, credential_key_id,
                              bypass_check,
                              dry_run=False):
        """Instantiate a mirror from a repository forge to github if it does
        not already exist.

        Args:
            repo_id: repository's identifier (callsign, phid or id).
                     This will be used to fetch information on the repository
                     to mirror.

            credential_key_id: the key the forge will use to push to
                               modifications to github

            dry_run: if True, inhibit the mirror creation (no write is
                    done to either github) or the forge.  Otherwise, the
                    default, it creates the mirror to github. Also, a
                    check is done to stop if a mirror uri is already
                    referenced in the forge about github.

        Returns:
            the repository instance whose mirror has been successfully
            mirrored. None if the mirror already exists.

        Raises:
            ValueError if some error occurred during any creation/reading step.
            The detail of the error is in the message.

        """
        token_forge = self.token_forge
        token_github = self.token_github
        forge_api_url = self.forge_url

        # Retrieve repository information
        if isinstance(repo_id, int):
                constraint_key = "ids"
        elif repo_id.startswith("PHID"):
            constraint_key = "phids"
        else:
            constraint_key = "callsigns"

        query = RepositorySearch(forge_api_url, token_forge)
        data = query.request(constraints={
            constraint_key: [repo_id],
        }, attachments={
            "uris": True
        })

        repository_information = data[0]

        # Check existence of mirror already set
        if mirror_exists(repository_information) and not bypass_check:
            if not bypass_check:
                return None
            print('** Bypassing check as requested **')

        # Retrieve exhaustive information on repository
        repo = retrieve_repo_information(repository_information)
        if not repo:
            raise ValueError('Error when trying to retrieve detailed'
                             ' information on the repository')

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

        query = PassphraseSearch(forge_api_url, token_forge)
        data = query.request(ids=[credential_key_id])

        # Retrieve the phid for that passphrase
        key_phid = list(data.values())[0]['phid']

        repo['url_github'] = 'git@github.com:SoftwareHeritage/%s.git' % (
            repo['name'])

        # Install the github mirror in the forge
        if not dry_run:
            query = DiffusionUriEdit(forge_api_url, token_forge)
            query.request(transactions=[
                {"type": "repository", "value": repo['phid']},
                {"type": "uri", "value": repo['url_github']},
                {"type": "io", "value": "mirror"},
                {"type": "display", "value": "never"},
                {"type": "disable", "value": False},
                {"type": "credential", "value": key_phid},
            ])

        return repo

    def mirror_repos_to_github(self, query_name, credential_key_id,
                               bypass_check, dry_run):
        """Mirror repositories to github.

        Args:
            credential_key_id: the key the forge will use to push to
                               modifications to github

            query_name: Query's name as per your phabricator forge's
                        setup.

            dry_run: if True, inhibit the mirror creation (no write is
                    done to either github) or the forge.  Otherwise, the
                    default, it creates the mirror to github. Also, a
                    check is done to stop if a mirror uri is already
                    referenced in the forge about github.

        Returns:
            dict with keys 'mirrored', 'skipped' and 'errors' keys.

        """
        token_forge = self.token_forge
        forge_api_url = self.forge_url

        query = RepositoriesToMirror(forge_api_url, token_forge)
        repositories = list(query.request(queryKey=query_name))

        if not repositories:
            return None

        for repo_id in repositories:
            assert repo_id is not None
            try:
                if dry_run:
                    print('** DRY RUN - %s **' % repo_id)

                repo = self.mirror_repo_to_github(
                    repo_id, credential_key_id, bypass_check, dry_run)

                if repo:
                    yield "Repository %s mirrored at %s." % (
                        repo['url'], repo['url_github'])
                else:
                    yield 'Mirror already configured for %s, stopping.' % (
                        repo_id)
            except Exception as e:
                yield str(e)


@click.group()
def cli(): pass


@cli.command()
@click.option('--repo-id',
              help="Repository's identifier (either callsign, id or phid)")
@click.option('--credential-key-id',
              help="""credential to use for access from phabricator's forge to
                      github""")
@click.option('--bypass-check/--no-bypass-check',
              help="""By default, the process of mirroring stops if a github
                      mirror already exists. This flag bypasses the check.
                   """)
@click.option('--dry-run/--no-dry-run', default=False)
def mirror(repo_id, credential_key_id, bypass_check, dry_run):
    """Shell interface to instantiate a mirror from a repository forge to
    github. Does nothing if the repository already exists.

    Args:
        repo_id: repository's identifier callsign. This will be
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
    mirror_forge = SWHMirrorForge()

    msg = ''
    try:
        if dry_run:
            print('** DRY RUN **')

        repo = mirror_forge.mirror_repo_to_github(
            repo_id, credential_key_id, bypass_check, dry_run)

        if repo:
            msg = "Repository %s mirrored at %s." % (
                repo['url'], repo['url_github'])
        else:
            msg = 'Mirror already configured for %s, stopping.' % repo_id
    except Exception as e:
        print(e)
        sys.exit(1)
    else:
        print(msg)
        sys.exit(0)


@cli.command()
@click.option('--query-repositories',
              help="""Name of the query that lists the repositories to mirror
                      in github.""")
@click.option('--credential-key-id',
              help="""credential to use for access from phabricator's forge to
                      github""")
@click.option('--bypass-check/--no-bypass-check',
              default=False,
              help="""By default, the process of mirroring stops if a github
                      mirror already exists. This flag bypasses the check.
                   """)
@click.option('--dry-run/--no-dry-run', default=False,
              help="""Do nothing but read and print what would
                      actually happen without the flag.""")
def mirrors(query_repositories, credential_key_id, bypass_check, dry_run):
    """Shell interface to instantiate mirrors from a repository forge to
    github. This uses the query_name provided to execute said query.
    The resulting repositories is then mirrored to github if not
    already mirrored.

    Args:
        credential_key_id: the key the forge will use to push to
                           modifications to github

        query_repositories: Query's name which lists the repositories to mirror
                           (as per phabricator forge's setup).

        dry_run: if True, inhibit the mirror creation (no write is
                done to either github) or the forge.  Otherwise, the
                default, it creates the mirror to github. Also, a
                check is done to stop if a mirror uri is already
                referenced in the forge about github.

    """
    mirror_forge = SWHMirrorForge()

    if dry_run:
        print('** DRY RUN **')

    for msg in mirror_forge.mirror_repos_to_github(
            query_name=query_repositories,
            credential_key_id=credential_key_id,
            bypass_check=bypass_check,
            dry_run=dry_run):
        print(msg)


if __name__ == '__main__':
    cli()
