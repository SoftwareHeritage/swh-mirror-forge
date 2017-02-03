swh-mirror-forge
================

Mirror swh's forge to github

# Configuration

In $SWH_CONFIG_PATH/mirror-forge/config.yml (SWH_CONFIG_PATH being one
of /etc/softwareheritage/,~/.config/swh, or ~/.swh/), add the
following information:

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
python3 -m swh.mirror.forge.sync --repo-callsign DMOD \
                                 --repo-name swh-model \
                                 --repo-url https://forge.softwareheritage.org/source/swh-model/ \
                                 --repo-description "" \
                                 --credential-key-id 3
```
