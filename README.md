# bkstg - Mini IDP

A lightweight desktop application for managing your software catalog, inspired by [Backstage](https://backstage.io/). No server required - just point it at your local Git repository.

## Demo

https://github.com/i2y/bkstg/raw/main/assets/demo.mp4

## Features

- Backstage-compatible YAML entity schema
- Local Git repository as data backend (no external database required)
- DuckDB for fast in-memory querying
- Dependency graph visualization with cycle detection
- Form-based entity editor
- Scorecard system for tracking entity health metrics
- Dashboard with charts and leaderboards
- Score/Rank history visualization with time-series graphs

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Usage

```bash
uv run bkstg [catalog-path]
```

If no path is provided, the current directory is used.

## Entity Kinds

- **Component**: Software units (services, libraries, websites)
- **API**: Interface definitions (OpenAPI, GraphQL, gRPC)
- **Resource**: Infrastructure (databases, caches, queues)
- **System**: Groups of related components
- **Domain**: Business domain contexts
- **User**: Team members
- **Group**: Teams and organizational units

## Catalog Structure

```
catalogs/
├── components/
├── apis/
├── resources/
├── systems/
├── domains/
├── users/
├── groups/
├── scorecards/
└── history/
    ├── scores/
    ├── ranks/
    └── definitions/
```

## Scorecard (bkstg Extension)

bkstg extends the Backstage schema with a scorecard system. Define scores in `metadata.scores`:

```yaml
metadata:
  name: my-component
  scores:
    - score_id: security
      value: 85
      reason: "Passed security audit"
```

Scorecard definitions in `catalogs/scorecards/` configure score metrics and rank formulas.

## License

MIT
