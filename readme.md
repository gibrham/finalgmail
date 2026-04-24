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

**Example:**

```bash
gcli search "invoice" --from sender@example.com --label Finance
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
```
