# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""Lower level api bindings to a phabricator forge api.

"""

import json

from abc import ABCMeta, abstractmethod
from subprocess import PIPE, Popen, check_output


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

        """
        return data

    def request(self, **kwargs):
        """Actual execution of the request.

        Note: Actual implementation depends on arcanist.  I Did not
        yet find the right way to use 'requests' with api token (that
        is no oauth session...)

        """
        query = dict(**kwargs)
        json_parameters = json.dumps(query)

        try:
            with Popen(['echo', json_parameters], stdout=PIPE) as dump:
                cmd = ['arc', 'call-conduit',
                       '--conduit-uri', self.forge_url,
                       '--conduit-token', self.api_token,
                       self.url()]
                json_response = check_output(cmd, stdin=dump.stdout,
                                             universal_newlines=True)
        except Exception as e:
            raise e
        else:
            if json_response:
                data = json.loads(json_response)

                if 'errorMessage' in data and data['errorMessage'] is not None:
                    raise ValueError("Error: %s" % data['errorMessage'])
                return self.parse_response(data['response'])
