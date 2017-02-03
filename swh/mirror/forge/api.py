# Copyright (C) 2017  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""Higher level api bindings to a phabricator forge.

"""

from .request import Request


class RepositorySearch(Request):
    def url(self):
        return 'diffusion.repository.search'

    def parse_response(self, data):
        return data['data']


class PassphraseSearch(Request):
    def url(self):
        return 'passphrase.query'

    def parse_response(self, data):
        return data['data']


class DiffusionUriEdit(Request):
    def url(self):
        return 'diffusion.uri.edit'
