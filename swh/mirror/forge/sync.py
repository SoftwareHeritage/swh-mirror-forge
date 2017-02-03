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
        print("""Install the phabricator forge's token in $SWH_CONFIG_PATH/mirror-forge/config.yml
(https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/).

Once the installation is done, you can trigger this script again.
        """)
        sys.exit(1)

    token_github = swh_mirror_forge.token_github
    if not token_github:
        print("""Install one personal github token in
$SWH_CONFIG_PATH/mirror-forge/config.yml with scope public_repo
(https://github.com/settings/tokens).

You must be associated to https://github.com/softwareheritage
organization.  Once the installation is done, you can trigger this
script again.
        """)
        sys.exit(1)

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
    """Given information on repository, extract the needed information for mirroring.

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


@click.command()
@click.option('--repo-callsign',
              help="Repository's callsign")
@click.option('--credential-key-id',
              help="credential to use for access from phabricator's forge to github")
@click.option('--dry-run/--no-dry-run', default=False)
def run(repo_callsign, credential_key_id, dry_run):
    """This will instantiate a mirror from a repository forge to github.

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
    ### Retrieve credential access to github and phabricator's forge
    token_forge, token_github = prepare_token()

    ### Retrieve repository information

    query = RepositorySearch(FORGE_API_URL, token_forge)
    data = query.request(constraints={
        "callsigns": [repo_callsign],
    }, attachments={
        "uris": True
    })

    ### Check existence of mirror already set

    # Also determine an uri to provide as original url in the github mirror

    repository_information = data[0]

    ### Create repository in github
    if not dry_run:
        if mirror_exists(repository_information):
            print('Mirror already configured for %s, stopping.' % repo_callsign)
            sys.exit(0)

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
            print("""Failure to create the repository in github.
Status: %s""" % r.status_code)
            sys.exit(1)

    repo = retrieve_repo_information(repository_information)

    ### Retrieve credential information

    query = PassphraseSearch(FORGE_API_URL, token_forge)
    data = query.request(ids=[credential_key_id])

    # Retrieve the phid for that passphrase
    key_phid = list(data.values())[0]['phid']

    repo['url_github'] = 'git@github.com:SoftwareHeritage/%s.git' % repo['name']

    ### Install the github mirror in the forge

    if not dry_run:
        query = DiffusionUriEdit(FORGE_API_URL, token_forge)
        data = query.request(transactions=[
            {"type": "repository", "value": repo['phid']},
            {"type": "uri", "value": repo['url_github']},
            {"type": "io", "value": "mirror"},
            {"type": "display", "value": "never"},
            {"type": "disable", "value": False},
            {"type": "credential", "value": key_phid},
        ])
    else:
        print("**dry run**")

    print("Repository %s mirrored at %s." % (repo['url'], repo['url_github']))
    sys.exit(0)


if __name__ == '__main__':
    run()
