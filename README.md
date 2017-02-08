swh-mirror-forge
================

Mirror swh's forge to github

# Configuration

In $SWH_CONFIG_PATH/mirror-forge/config.yml (SWH_CONFIG_PATH being in
{/etc/softwareheritage/,~/.config/swh, ~/.swh/}), add the following
information:

```yaml
github: <github-api-token>
forge: <forge-api-token>
```

Docs:
- github: https://github.com/settings/tokens
- swh forge: https://forge.softwareheritage.org/settings/user/<your-user>/page/apitokens/

# Use

## mirror only

Providing one identifier (id, phid or callsign) of a repository:

```sh
python3 -m swh.mirror.forge.sync mirror --repo-id DMOD --credential-key-id 3 --dry-run
```

This will (providing you remove the --dry-run flag):

- retrieve information on the repository identified by the callsign
  provided as parameter (--repo-callsign).

- determine the repository's name, repository's forge's url,
  repository's description

- create an empty repository in github with the same name, description
  and pointing back to the origin fork using the phabricator url

- associate the github uri in the phabricator forge as a mirror. This
  uses the credential key information provided as parameter (--credential-key)

All of this will lead to phabricator pushing regularly the changes to
the mirror in github.

## Through query repository listing

Providing one query:

```sh
python3 -m swh.mirror.forge.sync mirrors --query-repositories z1zwaVy_tEDt --credential-key-id 3 --dry-run
```

This will (providing you remove the --dry-run flag):

- execute the query which is supposed to return the list of
  repositories we want to mirror

- then loop over each repository to mirror them as described in
  previous paragraph
