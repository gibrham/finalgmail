# gcli

Secure Gmail CLI built with Typer.

## Install

```bash
pip install -e ".[dev]"
```

This project uses the `ladybug` graph database package to materialize extracted relationship graphs.

## Setup

1. Create `./credentials/secrets.json` from your Google OAuth desktop app credentials.
2. Run:

```bash
gcli init
```

This opens the OAuth flow in a browser and writes `./credentials/token.json`.

## Commands

### gcli search

Searches across all mail with free terms and optional filters.

**Usage:**

```bash
gcli search <name> [options]
```

**Options:**

- `--from`: Filter by sender
- `--to`: Filter by recipient
- `--subject`: Filter by subject
- `--has-words`: Filter by words in the body
- `--label`: Filter by label
- `--after`: Filter by date after
- `--before`: Filter by date before
- `--artifact`: Save results to `.artifacts/search_<ulid>.jsonl`

**Example:**

```bash
gcli search "invoice" --from sender@example.com --label Finance
```

Create an explicit output artifact:

```bash
gcli search "invoice" --artifact
```

### gcli tag create

Creates labels, supporting nested labels like Parent/Child. Creates missing parents safely.

**Usage:**

```bash
gcli tag create <name>
```

**Example:**

```bash
gcli tag create "Projects/2026"
```

### gcli tools exall

Extracts sender/recipient communication and content mentions from a `search` artifact, then builds a directional email relationship graph model:

- Node type: `EmailAddress`
- Edge types:
  - `SENT_TO` (`from` sender → `to`/`cc`/`bcc` recipients)
  - `MENTIONS` (sender → email addresses mentioned in content)

**Usage:**

```bash
gcli tools exall --input-artifact <artifact-id-or-path> [options]
```

**Options:**

- `--input-artifact <id-or-path>`: Upstream artifact id or file path
- `--artifact`: Save graph payload to `.artifacts/exall_<ulid>.jsonl`

**Examples:**

```bash
gcli tools exall --input-artifact search_01JXXXXXXXXXXXXXXX

gcli tools exall \
  --input-artifact .artifacts/search_01JXXXXXXXXXXXXXXX.jsonl \
  --artifact
```

### gcli tools visualize

Builds an interactive Cytoscape.js HTML graph from an `exall` artifact.

**Usage:**

```bash
gcli tools visualize --input-artifact <artifact-id-or-path> [options]
```

**Options:**

- `--input-artifact <id-or-path>`: Graph artifact id or file path
- `--output <path>`: Output HTML file path (default `.artifacts/visualize_<ulid>.html`)

**Examples:**

```bash
gcli tools visualize --input-artifact exall_01JXXXXXXXXXXXXXXX
gcli tools visualize --input-artifact exall_01JXXXXXXXXXXXXXXX --output ./reports/email-graph.html
```

### gcli run

Runs a named pipeline from JSON configuration and orchestrates command execution with upfront input collection.

Pipeline runs precompute a single ULID and derive explicit artifact ids up front (`search_<ulid>`, `exall_<ulid>`, `visualize_<ulid>.html`) so each downstream step knows exactly which upstream artifact to consume.

**Usage:**

```bash
gcli run <pipeline_name> [options]
```

**Options:**

- `--from <step>`: Start from a step id
- `--until <step>`: Stop after a step id
- `--verbose`: Print detailed step logs and command execution lines
- `--iext`: Interactive extended mode (prompts optional user inputs too)
- `--input/-i key=value`: Provide upfront input values (can be repeated)

**Example pipeline:** `emailgph`

```bash
gcli run emailgph --input search.terms="invoice"
gcli run emailgph --iext
gcli run emailgph --from extract --until visualize \
  --input search.terms="invoice" \
  --input extract.input_artifact="search_01JXXXXXXXXXXXXXXX"
```
