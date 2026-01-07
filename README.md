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
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      GitHub                load on startup             │
    │                                                                        │
    │  ┌─────────────┐ pull/push  ┌─────────────┐                            │
    │  │ Central     │◄──────────►│ Clone       │────────────────────────────┘
    │  │ Repo (src)  │            │ (GitHub Src)│ load
    │  └─────────────┘            └─────────────┘
    │        │                      ~/.bkstg-clones/
    │        │ Location refs
    │        ▼
    │  ┌─────────────┐ pull/push  ┌─────────────┐
    │  │ Team A      │◄───PR────►│ Clone       │─────────────────────────────┐
    │  │ Repo        │            │ (Location)  │ load                       │
    │  └─────────────┘            └─────────────┘                            │
    │        ▲                                                               │
    │  ┌─────────────┐ pull/push        │                                    │
    │  │ Team B      │◄───PR────────────┘                                    │
    │  │ Repo        │    Auto-cloned from Location targets                  │
    │  └─────────────┘    in central repo                                    │
    │                                                                        │
    └────────────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
- **Startup**: Central Repo Clone + Location Clones → DuckDB
- **Browse/Search**: User ↔ UI ↔ DuckDB (fast queries)
- **Edit**: UI → Clone directory (with auto-commit)
- **Sync Sources**: Pull/Push directly between Clone and Remote
- **Sync Locations**: Pull/Push or Create PR for Location clones

## Demo

https://github.com/i2y/bkstg/raw/main/assets/demo.mp4

## Features

### Catalog Management

- 7 entity types: Component, API, Resource, System, Domain, User, Group
- Form-based editor for easy YAML editing
- Full-text search across all entities
- Location entities for multi-repository aggregation

### Multi-Language Support

- 5 languages: English, Japanese, Traditional Chinese, Simplified Chinese, Korean
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

bkstg supports two ways to connect GitHub repositories:

| Method | Purpose | Edit | Sync |
|--------|---------|------|------|
| **GitHub Source** | Primary catalog storage | ✅ Yes | ✅ Pull/Push (direct) |
| **Location Entity** | Team catalogs via central repo | ✅ Yes | ✅ Pull/Push/PR |

#### Recommended: Central Repository Architecture

For organizations with multiple teams, we recommend a **central repository** model:

```
Central Repo (configured as GitHub Source)
├── scorecards/           ← Score/Rank definitions (shared)
├── locations/            ← References to team repositories
│   ├── team-a.yaml       → github.com/org/team-a-catalog
│   └── team-b.yaml       → github.com/org/team-b-catalog
└── components/           ← Shared entities

Team A Repo (via Location → auto-cloned)
├── components/           ← Editable by Team A
└── apis/                 ← Editable by Team A

Team B Repo (via Location → auto-cloned)
├── components/           ← Editable by Team B
└── systems/              ← Editable by Team B
```

**Benefits:**
- All teams share the same scorecard definitions
- Each team can edit their own entities
- Changes sync via Pull/Push or PR workflows
- Central repo maintains Location references

#### GitHub Source (for primary storage)

Configure your primary catalog in Settings → Sources:

1. Go to **Settings → Sources**
2. Click **+ GitHub**
3. Enter owner/repo/branch
4. Enable sync options as needed

Entities from GitHub Sources are fully editable with auto-commit and Pull/Push support.

#### Location Entity (for team catalogs)

Location entities reference external repositories. **bkstg automatically clones these repositories**, making all entities editable:

```yaml
# catalogs/locations/team-a.yaml
apiVersion: backstage.io/v1alpha1
kind: Location
metadata:
  name: team-a-catalog
spec:
  type: url
  target: https://github.com/org/team-a-catalog/blob/main/catalog-info.yaml
```

Features:
- **Auto-clone**: GitHub URLs are automatically cloned to `~/.bkstg-clones/`
- **Editable**: All entities from Location targets are editable
- **Sync support**: Pull, Push, and Create PR available in Sync panel
- **Central repo only**: Location entities are only processed from the central GitHub Source (not from team repos)
- **Duplicate handling**: First-loaded entity wins; later duplicates skipped

#### Sync Workflow for Location Clones

When you edit an entity from a Location target:

1. Changes are saved to the local clone (`~/.bkstg-clones/owner_repo_branch/`)
2. Changes are auto-committed to the local clone
3. Use **Sync panel** to Push or Create PR:
   - **Push**: Direct push if you have write access
   - **Create PR**: Opens a PR for review (recommended for team catalogs)

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

### Quick Try (Demo Repository)

Try bkstg with our demo repository:

1. Create `bkstg.yaml` in your working directory:

```yaml
version: 1
sources:
  - name: demo
    type: github
    owner: i2y
    repo: bkstg-demo
    branch: main
    path: catalogs
    enabled: true
    sync_enabled: true     # Uses local clone for fast startup
    auto_commit: false
```

2. Run bkstg:

```bash
uv run bkstg
```

On first run, bkstg clones the repository (sparse checkout). Subsequent starts are fast (~0.5s) as it uses the local clone.

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

### Starting Fresh

bkstg requires a GitHub Source to be configured. To start with your own catalog:

1. Create a new GitHub repository for your catalog
2. Configure it in `bkstg.yaml` (see examples above)
3. Run bkstg and start creating entities

All data is stored in your GitHub repository - no local files to clean up.

### Configuration Reference

Full `bkstg.yaml` options:

```yaml
version: 1
sources:
  # GitHub repository (required - this is your central catalog)
  - name: my-catalog
    type: github
    owner: myorg
    repo: software-catalog
    branch: main
    path: catalogs
    enabled: true
    sync_enabled: true    # Enable Pull/Push/PR
    auto_commit: true     # Auto-commit on save

settings:
  locale: auto            # UI language: auto, en, ja, zh-Hant, zh-Hans, ko
  cache_ttl: 300          # Location cache TTL in seconds
  max_workers: 5          # Parallel fetch workers
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
