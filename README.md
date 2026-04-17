# pr-search-cli

Thin CLI client for the PR similarity API.

Default deployment target:

- API: `https://evalstate-openclaw-pr-api.hf.space`
- repo: `openclaw/openclaw`

## Install / run

Run without installing permanently:

```bash
uvx pr-search-cli repo status
uvx pr-search-cli analysis status
uvx pr-search-cli analysis pr 67144
uvx pr-search-cli similar 67144
uvx pr-search-cli clusters 67144
uvx pr-search-cli cluster list --limit 20
```

Run the `pr-search` script from this package explicitly:

```bash
uvx --from pr-search-cli pr-search repo status
```

## Commands

```text
pr-search repo status
pr-search analysis status
pr-search analysis pr <number>
pr-search analysis meta-bugs
pr-search analysis meta-bug <cluster-id>
pr-search analysis duplicate-prs
pr-search analysis best
pr-search similar <number>
pr-search clusters <number>
pr-search cluster list
pr-search cluster view <cluster-id>
```

Useful flags:

- `--base-url`
- `-R, --repo`
- `--json`

`pr similar` and `pr clusters` also support:

- `--mode auto|indexed|live`

## Examples

```bash
pr-search repo status
pr-search analysis status
pr-search analysis pr 67144
pr-search similar 67144
pr-search clusters 67144
pr-search cluster list --limit 20
pr-search --json similar 67144 --mode live
pr-search --base-url http://127.0.0.1:7860 repo status
```

`similar` and `clusters` use `--mode auto` by default:

- `auto`
  - use indexed lookup when the PR is already in the active snapshot
  - otherwise fall back to live lookup via the server's configured live source
- `indexed`
  - require the PR to exist in the active snapshot
- `live`
  - force live lookup

## Publish

Build artifacts:

```bash
uv build
```

Publish to PyPI:

```bash
uv publish
```
