# bkstg - Mini IDP

> A serverless desktop Internal Developer Portal.
> Backstage-compatible, zero infrastructure required.

## Highlights

- **Zero Server** - Git repo + DuckDB (in-memory) = no backend needed
- **Backstage Compatible** - Use existing YAML catalogs as-is
- **Rich Visualization** - Dependency graphs, dashboards, heatmaps
- **GitHub Sync** - Bidirectional sync with Pull/Push/PR workflows

## Architecture

```
┌──────┐  browse / edit / search   ┌──────────────────────────────┐
│ User │ ◄────────────────────────►│         Desktop App          │
└──────┘                           │                              │
                                   │  ┌────────┐      ┌────────┐  │
                                   │  │   UI   │◄────►│ DuckDB │  │
                                   │  │Castella│ query│in-memory│ │
                                   │  └───┬────┘      └────────┘  │
                                   └──────┼───────────────▲───────┘
                                          │               │
                        ┌─────────────────┼───────────────┼─────────────────┐
                        │                 │  load on      │                 │
                        ▼                 │  startup      │                 │
              ┌─────────────────┐         │               │                 │
              │   Local YAML    │─────────┘               │                 │
              │   catalogs/     │                         │                 │
              └─────────────────┘                         │                 │
                                                          │                 │
    ┌─────────────────────────────────────────────────────┼─────────────────┤
    │                      GitHub                         │                 │
    │                                                     │                 │
    │  ┌─────────────┐ pull/push  ┌─────────────┐        │                 │
    │  │  Repo A     │◄──────────►│  Clone A    │────────┘                 │
    │  │  (sync)     │            │             │ load                     │
    │  └─────────────┘            └─────────────┘                          │
    │                               ~/.bkstg-clones/                       │
    │  ┌─────────────┐ pull/push  ┌─────────────┐                          │
    │  │  Repo B     │◄──────────►│  Clone B    │──────────────────────────┘
    │  │  (sync)     │            │             │ load
    │  └─────────────┘            └─────────────┘
    │
    │  ┌─────────────┐   fetch    ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
    │  │  Repo C     │───────────►  External Location (read-only)       │
    │  │  (external) │            │ Referenced via Location entities    │
    │  └─────────────┘            └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
    │                                       │
    └───────────────────────────────────────┼───────────────────────────────
                                            │ fetch via gh CLI
                                            ▼
                                     Load into DuckDB
```

**Data Flow:**
- **Startup**: Local YAML + GitHub Clones → DuckDB (in-memory)
- **Browse/Search**: User ↔ UI ↔ DuckDB (fast queries)
- **Edit**: UI → Local YAML or GitHub Clone (with auto-commit)
- **Sync**: Pull/Push between Clones and Remote Repos
- **External**: Location entities fetch from any GitHub repo (read-only)

## Demo

https://github.com/i2y/bkstg/raw/main/assets/demo.mp4

## Features

### Catalog Management

- 7 entity types: Component, API, Resource, System, Domain, User, Group
- Form-based editor for easy YAML editing
- Full-text search across all entities
- Location entities for multi-repository aggregation

### Multi-Language Support

- English and Japanese UI
- Auto-detect from OS language settings
- Change language in Settings without restart

### Dependency Graph

- Interactive visualization with pan/zoom
- Automatic cycle detection with warnings
- Click nodes to navigate between entities
- Visual relationship mapping (owns, depends on, provides API, etc.)

### Scorecard System (bkstg Extension)

bkstg extends Backstage with a powerful scorecard system:

- **Custom Scores**: Define metrics like security, documentation, testing
- **Rank Formulas**: Calculate ranks with customizable formulas
- **Threshold Labels**: S/A/B/C/D rankings based on score thresholds
- **History Tracking**: Track score and rank changes over time

```yaml
# Example: metadata.scores in entity YAML
metadata:
  name: my-component
  scores:
    - score_id: security
      value: 85
      reason: "Passed security audit"
```

### Dashboard

A comprehensive dashboard with multiple views:

| Tab | Description |
|-----|-------------|
| **Overview** | Entity counts, scored entities, average scores |
| **Charts** | Bar charts (by kind), Pie charts (rank distribution), Gauge (overall score) |
| **Heatmaps** | Kind × Score matrix, Entity × Score matrix with rank labels |
| **History** | Time-series graphs for scores and ranks, definition change tracking |
| **Leaderboard** | Top entities ranked by each metric |

### GitHub Sync

Bidirectional synchronization with GitHub repositories:

- Pull changes from remote repositories
- Push local changes with auto-commit
- Automatic conflict detection via dry-run merge
- Create PRs when conflicts occur
- Score and history data synchronized alongside entities

### Multi-Repository Support

- **Location entities** aggregate catalogs from multiple GitHub repos
- **Parallel fetching** for improved performance
- **Nested locations** support (Location → Location → entities)
- **Caching** with configurable TTL

### Location Entities

Location entities aggregate catalogs from external GitHub repositories.

#### Setup

1. Authenticate with GitHub CLI:
   ```bash
   gh auth login
   ```

2. Create a Location YAML in `catalogs/locations/`:
   ```yaml
   apiVersion: backstage.io/v1alpha1
   kind: Location
   metadata:
     name: external-team-catalog
     description: External team's catalog
   spec:
     type: url
     target: https://github.com/org/repo/blob/main/catalog-info.yaml
   ```

3. Restart bkstg to load the external catalog.

#### Supported URL Formats

- Single file: `spec.target: https://github.com/org/repo/blob/branch/path/to/file.yaml`
- Multiple files: `spec.targets: [url1, url2, ...]`

#### Features

- Recursive loading (Location → Location → entities)
- In-memory caching (default 5 minutes, configurable via `cache_ttl`)
- Circular reference detection

## Getting Started

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [GitHub CLI](https://cli.github.com/) (`gh`) for GitHub features

### Installation

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

### Quick Try (with samples)

bkstg includes sample catalogs to explore immediately:

```bash
uv run bkstg
```

This loads sample entities from `catalogs/` directory. Browse around to see how it works.

### Setup with GitHub (recommended)

For production use, connect bkstg to your GitHub repository.

#### Prerequisites

Authenticate with GitHub CLI:

```bash
gh auth login
```

#### Option A: Connect existing catalog repository

If you already have a Backstage-compatible catalog in GitHub:

1. Create `bkstg.yaml` in your project root:

```yaml
version: 1
sources:
  - name: my-catalog
    type: github
    owner: your-org        # GitHub org or username
    repo: your-catalog     # Repository name
    branch: main
    path: catalogs         # Path to catalog directory in repo
    enabled: true
    sync_enabled: true     # Enable Pull/Push
    auto_commit: true      # Auto-commit on save
```

2. Run bkstg:

```bash
uv run bkstg
```

#### Option B: Create new catalog repository

Starting fresh with a new catalog:

1. Create a new GitHub repository for your catalog

2. Create `bkstg.yaml`:

```yaml
version: 1
sources:
  - name: my-catalog
    type: github
    owner: your-org
    repo: your-new-catalog
    branch: main
    path: catalogs
    enabled: true
    sync_enabled: true
    auto_commit: true
```

3. Run bkstg and create entities using the UI. Changes will be pushed to your repository.

### Cleanup Sample Data

To remove sample data and start with a clean slate:

1. Delete sample entities:

```bash
rm -rf catalogs/components/*.yaml
rm -rf catalogs/apis/*.yaml
rm -rf catalogs/resources/*.yaml
rm -rf catalogs/systems/*.yaml
rm -rf catalogs/domains/*.yaml
rm -rf catalogs/users/*.yaml
rm -rf catalogs/groups/*.yaml
rm -rf catalogs/scorecards/*.yaml
rm -rf catalogs/history/
```

2. Edit `catalogs/locations/external.yaml` to configure your external repositories (or leave `targets: []` if not needed).

### Configuration Reference

Full `bkstg.yaml` options:

```yaml
version: 1
sources:
  # Local catalog directory
  - name: local
    type: local
    path: catalogs
    enabled: true

  # GitHub repository with sync
  - name: my-github-catalog
    type: github
    owner: myorg
    repo: software-catalog
    branch: main
    path: catalogs
    enabled: true
    sync_enabled: true    # Enable Pull/Push/PR
    auto_commit: true     # Auto-commit on save

settings:
  locale: auto            # UI language: auto, en, ja
  cache_ttl: 300          # Location cache TTL in seconds
  max_workers: 4          # Parallel fetch workers
  github_org: myorg       # GitHub org for user/group import
```

## Catalog Structure

```
catalogs/
├── components/       # Service definitions
├── apis/             # API specifications
├── resources/        # Infrastructure resources
├── systems/          # System groupings
├── domains/          # Business domains
├── users/            # Team members
├── groups/           # Teams
├── locations/        # Multi-repo aggregation
├── scorecards/       # Score/rank definitions
└── history/          # Score/rank history
    ├── scores/
    ├── ranks/
    └── definitions/
```

## Entity Kinds

| Kind | Description |
|------|-------------|
| **Component** | Software units (services, libraries, websites) |
| **API** | Interface definitions (OpenAPI, GraphQL, gRPC) |
| **Resource** | Infrastructure (databases, caches, queues) |
| **System** | Groups of related components |
| **Domain** | Business domain contexts |
| **User** | Team members |
| **Group** | Teams and organizational units |
| **Location** | References to external catalogs |

## Tech Stack

| Component | Technology |
|-----------|------------|
| **UI Framework** | [Castella](https://github.com/i2y/castella) (Declarative cross-platform Python UI with AI agent enablement) |
| **Database** | DuckDB (in-memory SQL for fast queries) |
| **GitHub CLI** | `gh` (authentication and API operations) |
| **Schema** | Pydantic models with Backstage compatibility |

## License

MIT
