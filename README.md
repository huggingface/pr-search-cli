# pr-search-cli

Standalone CLI client for the PR search API.

Default deployment target:

- API: `https://evalstate-openclaw-pr-api.hf.space`
- repo: `openclaw/openclaw`

When `--base-url` is omitted, the CLI now infers the Hugging Face Space host from `--repo`
by convention:

- `openclaw/openclaw` -> `https://evalstate-openclaw-pr-api.hf.space`
- `huggingface/transformers` -> `https://evalstate-transformers-pr-api.hf.space`
- `huggingface/diffusers` -> `https://evalstate-diffusers-pr-api.hf.space`

You can also set a default API host with:

```bash
export PR_SEARCH_BASE_URL=https://evalstate-transformers-pr-api.hf.space
```

Resolution order:

1. explicit `--base-url`
2. `PR_SEARCH_BASE_URL`
3. inferred host from `--repo`
4. fallback default deployment target

## Install / run

Run without installing permanently:

```bash
uvx pr-search-cli status
uvx pr-search-cli code similar 67144
uvx pr-search-cli code clusters for-pr 67144
uvx pr-search-cli issues list
uvx pr-search-cli contributors show alice
```

Run the `pr-search` script from this package explicitly:

```bash
uvx --from pr-search-cli pr-search status
```

## CLI overview

```text
pr-search status

pr-search code status
pr-search code similar <pr-number>
pr-search code clusters list
pr-search code clusters show <cluster-id>
pr-search code clusters for-pr <pr-number>

pr-search issues status
pr-search issues list
pr-search issues show <cluster-id>
pr-search issues for-pr <pr-number>
pr-search issues contains-pr <pr-number> [cluster-id]
pr-search issues duplicate-prs
pr-search issues best

pr-search contributors status
pr-search contributors list
pr-search contributors show <login>
pr-search contributors risk <login>
```

The old `repo ...`, `similar`, `clusters`, `cluster ...`, and `analysis ...`
commands are still accepted as hidden compatibility aliases.

## Useful flags

Global flags:

- `--base-url`
- `-R, --repo`
- `PR_SEARCH_BASE_URL` environment variable
- `--format text|json|jsonl|ids`
- `--json` (compatibility alias for `--format json`)

Lookup commands also support:

- `--mode auto|indexed|live`

Issue-cluster commands also support:

- `--variant auto|hybrid|deterministic`

## Examples

```bash
pr-search status
pr-search -R huggingface/transformers status
pr-search -R huggingface/transformers code similar 44940
pr-search -R huggingface/diffusers issues list
PR_SEARCH_BASE_URL=https://evalstate-transformers-pr-api.hf.space pr-search status
pr-search code status
pr-search code similar 67144 --mode live
pr-search code clusters list --limit 20
pr-search issues list --variant auto
pr-search issues for-pr 67144
pr-search issues contains-pr 67144 issue-cluster-44861-3
pr-search contributors list --format jsonl
pr-search contributors risk alice --format json
pr-search --base-url http://127.0.0.1:7860 status
```

## Output formats

- `text`
  - stable key/value blocks and tables for humans and shell users
- `json`
  - full API payload
- `jsonl`
  - one JSON object per list row when the command returns a collection
- `ids`
  - just the primary identifiers from list-like commands

## Publish

Build artifacts:

```bash
uv build
```

Publish to PyPI:

```bash
uv publish
```
