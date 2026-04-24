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

```bash
gcli search "invoice" --from sender@example.com --label Finance
gcli tag create "Projects/2026"
```
