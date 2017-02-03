# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import click
import json
import os
import sys
import requests

from .api import RepositorySearch, PassphraseSearch, DiffusionUriEdit


FORGE_API_URL = 'https://forge.softwareheritage.org'


def load_token_from_file(filepath):
    """Loading the token."""
    with open(filepath, 'r') as f:
        return f.read().strip()


def prepare_token():
    """Prepare the needed token from the disk.

    Returns:
        tuple (token-forge, token-github)

    """
    token_forge_filepath = os.getenv("HOME") + '/.config/swh/forge-token'
    token_forge = load_token_from_file(token_forge_filepath)
    if not token_forge:
        print("""Install the phabricator forge's token in %s
(https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/).

Once the installation is done, you can trigger this script again.
        """ % token_forge_filepath)
        sys.exit(1)

    token_github_filepath = os.getenv("HOME") + '/.config/swh/github-token'
    token_github = load_token_from_file(token_github_filepath)
    if not token_github:
        print("""Install one personal github token in %s with scope
public_repo (https://github.com/settings/tokens).

You must be associated to https://github.com/softwareheritage
organization.  Once the installation is done, you can trigger this
script again.
        """ % token_github_filepath)
        sys.exit(1)

    return token_forge, token_github


@click.command()
@click.option('--repo-callsign',
              help="Repository's callsign")
@click.option('--repo-name',
              help="Repository name (used in github)")
@click.option('--repo-url',
              help="Repository's forge url (used in github)")
@click.option('--repo-description',
              help="Repository's description (used in github)")
@click.option('--credential-key-id',
              help="credential to use for access from phabricator's forge to github")
@click.option('--github/--nogithub', default=True)
def run(repo_callsign, repo_name, repo_url, repo_description,
        credential_key_id, github):
    """This will instantiate a mirror from a repository forge to github.

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

    repo_phid = data[0]['phid']

    ### Check existence of mirror already set

    for uri in data[0]['attachments']['uris']['uris']:
        for url in uri['fields']['uri'].values():
            if 'github' in url:
                print('Mirror already installed at %s, stopping.' % url)
                sys.exit(0)

    ### Create repository in github
    if github or mirror:
        r = requests.post(
            'https://api.github.com/orgs/SoftwareHeritage/repos',
            headers={'Authorization': 'token %s' % token_github},
            data=json.dumps({
                "name": repo_name,
                "description": repo_description,
                "homepage": repo_url,
                "private": False,
                "has_issues": False,
                "has_wiki": False,
                "has_downloads": True
            }))

        if not r.ok:
            print("""Failure to create the repository in github.
Status: %s""" % r.status_code)
            sys.exit(1)

    ### Retrieve credential information

    query = PassphraseSearch(FORGE_API_URL, token_forge)
    data = query.request(ids=[credential_key_id])

    # Retrieve the phid for that passphrase
    key_phid = list(data.values())[0]['phid']

    repo_url_github = 'git@github.com:SoftwareHeritage/%s.git' % repo_name

    ### Install the github mirror in the forge

    query = DiffusionUriEdit(FORGE_API_URL, token_forge)
    data = query.request(transactions=[
        {"type": "repository", "value": repo_phid},
        {"type": "uri", "value": repo_url_github},
        {"type": "io", "value": "mirror"},
        {"type": "display", "value": "never"},
        {"type": "disable", "value": False},
        {"type": "credential", "value": key_phid},
    ])

    print("Repository %s mirrored at %s." % (repo_url, repo_url_github))
    sys.exit(0)


if __name__ == '__main__':
    run()
