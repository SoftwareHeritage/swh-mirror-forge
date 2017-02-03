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

For now, on a per repository basis:

```sh
python3 -m swh.mirror.forge.sync --repo-callsign DMOD --credential-key-id 3
```

# What does this do?

- Retrieve information on the repository identified by the callsign
  provided as parameter (--repo-callsign).

- Determine the repository's name, repository's forge's url,
  repository's description

- Create an empty repository in github with the same name, description
  and pointing back to the origin fork using the phabricator url

- Associate the github uri in the phabricator forge as a mirror. This
  uses the credential key information provided as parameter (--credential-key)
