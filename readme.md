# gcli

Secure Gmail CLI built with Typer.

## Install

```bash
pip install -e ".[dev]"
```

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
