# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""Lower level api bindings to a phabricator forge api.

"""

import requests

from abc import ABCMeta, abstractmethod


class Request(metaclass=ABCMeta):
    """Class in charge of providing connection request to forge's api.

    """
    def __init__(self, forge_url, api_token):
        self.forge_url = forge_url
        self.api_token = api_token

    @abstractmethod
    def url(self):
        """Api url (e.g diffusion.findsymbols, repository.search,
           repository.edit.uri, etc...)

        """
        pass

    def parse_response(self, data):
        """Parsing the query response. By default, identity function.

        Args:
            data: dict of data returned by the post query to
            phabricator's api.

        Returns:
            Dict transformed or not.

        """
        return data['data']

    def post(self, body):
        """Actual execution of the request.

        Args:
            body: the payload of the request.

        """
        body['api.token'] = self.api_token

        r = requests.post('%s/api/%s' % (self.forge_url, self.url()),
                          data=body)

        if r.ok:
            data = r.json()
            if 'error_code' in data and data['error_code'] is not None:
                raise ValueError("Error: %s - %s" % (
                    data['error_code'], data['error_info']))

            return self.parse_response(data['result'])

        if 'error_code' in data and data['error_code'] is not None:
            raise ValueError("Error: %s - %s" % (
                data['error_code'], data['error_message']))


class RepositorySearch(Request):
    """Abstraction over the repository search api call.

    """
    def url(self):
        return 'diffusion.repository.search'


class PassphraseSearch(Request):
    """Abstraction over the passphrase search api call.

    """
    def url(self):
        return 'passphrase.query'


class DiffusionUriEdit(Request):
    """Abstraction over the diffusion uri edition api call.

    """
    def url(self):
        return 'diffusion.uri.edit'

    def parse_response(self, data):
        return data


class RepositoriesToMirror(RepositorySearch):
    """Specific query to repository search api to yield ids (callsigns,
       id, phid) of repository to mirror.

    """
    def parse_response(self, data):
        data = super().parse_response(data)
        for entry in data:
            fields = entry['fields']
            repo = {
                'name': fields['name']
            }
            if 'id' in entry:
                repo['id'] = entry['id']
            elif 'phid' in entry:
                repo['id'] = entry['phid']
            elif 'callsign' in fields:
                repo['id'] = fields['callsign']
            else:
                continue
            yield repo
