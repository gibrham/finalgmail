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
- `--cache`: Save results to `.cache/search_<timestamp>.jsonl`

**Example:**

```bash
gcli search "invoice" --from sender@example.com --label Finance
```

Cache for chaining:

```bash
gcli search "invoice" --cache
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

Extracts sender/recipient communication and content mentions from cached search results, then builds a directional email relationship graph model:

- Node type: `EmailAddress`
- Edge types:
  - `SENT_TO` (`from` sender → `to`/`cc`/`bcc` recipients)
  - `MENTIONS` (sender → email addresses mentioned in content)

**Usage:**

```bash
gcli tools exall [options]
```

**Options:**

- `--from-cache <command>`: Load latest cache from the specified command (default upstream is `search`)
- `--cache`: Save graph output to `.cache/exall_<timestamp>.jsonl`

**Examples:**

```bash
gcli tools exall
gcli tools exall --from-cache search
gcli tools exall --cache
```

### gcli tools visualize

Builds an interactive Cytoscape.js HTML graph from cached `exall` output.

**Usage:**

```bash
gcli tools visualize [options]
```

**Options:**

- `--from-cache <command>`: Load latest cache from command (default `exall`)
- `--output <path>`: Output HTML file path (default `graph.html`)

**Examples:**

```bash
gcli tools visualize
gcli tools visualize --output ./reports/email-graph.html
gcli tools visualize --from-cache exall --output graph.html
```

### gcli run

Runs a named pipeline from JSON configuration and orchestrates command execution with upfront input
collection.

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
gcli run emailgph --from extract --until visualize --input search.terms="invoice"
```
