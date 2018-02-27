# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import json
import sys
import requests

from swh.core.config import SWHConfig
from .request import RepositorySearch, PassphraseSearch
from .request import DiffusionUriEdit, RepositoriesToMirror


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
        if 'github' in effective_url and \
           not effective_url.endswith('github.git'):
            return True

    return False


def format_repo_information(data, forge_base_url, github_org_name):
    """Given information on repository, extract the needed information for
       mirroring.

    Args:
        data: full information on the repository
        org_name: The github organization name

    Returns:
        dict with keys phid, description, url, name.

    """
    name = None
    url = None
    forge_base_url = forge_base_url.rstrip('/')
    if data['fields']['shortName']:
        name = data['fields']['shortName']
        url = '%s/source/%s/' % (forge_base_url, data['fields']['shortName'])
    elif data['fields']['callsign']:
        name = data['fields']['callsign']
        url = '%s/diffusion/%s/' % (forge_base_url, data['fields']['callsign'])
    else:
        name = 'R%s' % data['id']
        url = '%s/diffusion/%s/' % (forge_base_url, data['id'])

    return {
        'phid': data['phid'],
        'description': data['fields']['name'],
        'url': url,
        'name': name,
        'url_github': 'git@github.com:%s/%s.git' % (github_org_name, name),
    }


class SWHMirrorForge(SWHConfig):
    """Class in charge of mirroring a forge to github.

    """
    CONFIG_BASE_FILENAME = 'mirror-forge/config'

    DEFAULT_CONFIG = {
        'forge': ('dict', {
            'api_token': None,
            'url': 'https://forge.softwareheritage.org',
        }),
        'github': ('dict', {
            'api_token': None,
            'org': 'SoftwareHeritage',
        })

    }

    def __init__(self):
        super().__init__()
        self.config = self.parse_config_file()
        self.forge_token = self.config['forge']['api_token']
        self.forge_url = self.config['forge']['url']
        self.github_token = self.config['github']['api_token']
        self.github_org = self.config['github']['org']
        self._check()

    def _check(self):
        """Check the needed tokens are set or fail with an explanatory
           message.

        """
        if not self.forge_token:
            raise ValueError("""Install the phabricator forge's token in
    $SWH_CONFIG_PATH/mirror-forge/config.yml
    (https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/).

    Once the installation is done, you can trigger this script again.""")

        if not self.github_token:
            raise ValueError("""Install one personal github token in
    $SWH_CONFIG_PATH/mirror-forge/config.yml with scope public_repo
    (https://github.com/settings/tokens).

    You must be associated to https://github.com/%s organization.
    Once the installation is done, you can trigger this
    script again.""" % self.github_org)

    def get_repo_info(self, repo_id):
        """Returns bare information on the repository identified by repo_id.

        Args:
            repo_id (int, str): Either id as int, phid as string or
                                callsign as string identifying uniquely a
                                repository.

        Returns:
            information on repository as dict.

        """
        # Retrieve repository information
        if isinstance(repo_id, int):
            constraint_key = "ids"
        elif repo_id.startswith("PHID"):
            constraint_key = "phids"
        else:
            constraint_key = "callsigns"

        data = RepositorySearch(self.forge_url, self.forge_token).post({
            'constraints[%s][0]' % constraint_key: repo_id,
            'attachments[uris]': True
        })

        return data[0]

    def create_or_update_repo_on_github(self, repo, update=False):
        """Create or update routine on github.

        Args:

            repo (dict): Dictionary of information on the repository.
            update (bool): Determine if we update the repository's
            information or not. Default to False (so creation).

        """

        if update:
            query_fn = requests.patch
            error_msg_action = 'update'
            api_url = 'https://api.github.com/repos/%s/%s' % (
                self.github_org, repo['name'])
        else:
            query_fn = requests.post
            error_msg_action = 'create'
            api_url = 'https://api.github.com/orgs/%s/repos' % self.github_org

        print(api_url)

        r = query_fn(
            url=api_url,
            headers={'Authorization': 'token %s' % self.github_token},
            data=json.dumps({
                "name": repo['name'],
                "description": 'GitHub mirror of ' + repo['description'],
                "homepage": repo['url'],
                "private": False,
                "has_issues": False,
                "has_wiki": False,
                "has_downloads": True
            }))

        if not r.ok:
            raise ValueError("""Failure to %s the repository '%s' in github.
Status: %s""" % (error_msg_action, repo['name'], r.status_code))

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
        repository_information = self.get_repo_info(repo_id)
        view_policy = repository_information['fields']['policy']['view']
        if view_policy != 'public':
            raise ValueError("Repository view policy for %s is not public" %
                             repo_id)

        # Check existence of mirror already set
        if mirror_exists(repository_information) and not bypass_check:
            if not bypass_check:
                return None
            print('** Bypassing check as requested **')

        # Retrieve exhaustive information on repository
        repo = format_repo_information(repository_information, self.forge_url,
                                       self.github_org)
        if not repo:
            raise ValueError('Error when trying to retrieve detailed'
                             ' information on the repository')

        # Create repository in github
        if not dry_run:
            self.create_or_update_repo_on_github(repo, update=False)

        # Retrieve credential information
        data = PassphraseSearch(self.forge_url, self.forge_token).post({
            'ids[0]': credential_key_id
        })

        # Retrieve the phid for that passphrase
        key_phid = list(data.values())[0]['phid']

        # Install the github mirror in the forge
        if not dry_run:
            DiffusionUriEdit(self.forge_url, self.forge_token).post({
                'transactions[0][type]': 'repository',
                'transactions[0][value]': repo['phid'],
                'transactions[1][type]': 'uri',
                'transactions[1][value]': repo['url_github'],
                'transactions[2][type]': 'io',
                'transactions[2][value]': 'mirror',
                'transactions[3][type]': 'display',
                'transactions[3][value]': 'never',
                'transactions[4][type]': 'disable',
                'transactions[4][value]': 'false',
                'transactions[5][type]': 'credential',
                'transactions[5][value]': key_phid,
            })

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
        repositories = list(
            RepositoriesToMirror(self.forge_url, self.forge_token).post({
                'queryKey': query_name}))

        if not repositories:
            return None

        for repo in repositories:
            repo_id = repo['id']
            try:
                if dry_run:
                    print("** DRY RUN - name '%s' ; id '%s' **" % (
                        repo['name'], repo_id))

                repo_detail = self.mirror_repo_to_github(
                    repo_id, credential_key_id, bypass_check, dry_run)

                if repo_detail:
                    yield "Repository %s mirrored at %s." % (
                        repo_detail['url'], repo_detail['url_github'])
                else:
                    yield 'Mirror already configured for %s, stopping.' % (
                        repo_id)
            except Exception as e:
                yield str(e)

    def update_mirror_info(self, repo_id, dry_run):
        """Given a repository identifier, retrieve information on such
           repository and update github information on that repository.

        """
        repository_information = self.get_repo_info(repo_id)

        # Retrieve exhaustive information on repository
        repo = format_repo_information(repository_information, self.forge_url,
                                       self.github_org)
        if not repo:
            raise ValueError('Error when trying to retrieve detailed'
                             ' information on the repository')

        if not dry_run:
            self.create_or_update_repo_on_github(repo, update=True)

        return repo

    def update_mirrors_info(self, query_name, dry_run):
        """Given a query name, loop over the repositories returned by such
           query execution and update information on github for those
           repositories.

        """
        repositories = list(
            RepositoriesToMirror(self.forge_url, self.forge_token).post({
                'queryKey': query_name}))

        if not repositories:
            return None

        for repo in repositories:
            repo_id = repo['id']
            try:
                if dry_run:
                    print("** DRY RUN - name '%s' ; id '%s' **" % (
                        repo['name'], repo_id))

                repo_detail = self.update_mirror_info(repo_id, dry_run)

                if repo_detail:
                    yield "Github mirror %s information updated." % (
                        repo_detail['url_github'])

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

    try:
        repo_id = int(repo_id)
    except Exception:
        pass

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


@cli.command()
@click.option('--repo-id',
              help="Repository's identifier (either callsign, id or phid)")
@click.option('--dry-run/--no-dry-run', default=False)
def update_github_mirror(repo_id, dry_run):
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

    try:
        repo_id = int(repo_id)
    except Exception:
        pass

    msg = ''
    try:
        if dry_run:
            print('** DRY RUN **')

        repo = mirror_forge.update_mirror_info(repo_id, dry_run)
        msg = "Github mirror information %s updated." % repo['url_github']
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
@click.option('--dry-run/--no-dry-run', default=False,
              help="""Do nothing but read and print what would
                      actually happen without the flag.""")
def update_github_mirrors(query_repositories, dry_run):
    """Shell interface to update mirrors information on github. This uses
    the query_name provided to execute said query.  The resulting
    repositories' github information is then updated.

    Args:
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

    for msg in mirror_forge.update_mirrors_info(
            query_repositories, dry_run=dry_run):
        print(msg)


if __name__ == '__main__':
    cli()
