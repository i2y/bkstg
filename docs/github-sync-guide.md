# GitHub Sync Guide

bkstg integrates with GitHub repositories to manage your catalog. This guide explains how the sync functionality works.

## Overview

The bkstg sync workflow:

```
Edit in UI → Save → Auto-commit locally → Push/Create PR in Sync panel
```

## Auto-Commit

### Behavior

When you save an entity or scorecard definition from the UI:

1. **YAML file is saved** - The file in the clone directory is updated
2. **Automatically committed** - If `auto_commit: true` (default)

### Configuration

Control auto-commit in `bkstg.yaml`:

```yaml
sources:
  - type: github
    owner: your-org
    repo: your-catalog
    branch: main
    name: my-catalog
    auto_commit: true   # Default: true
```

| Setting | Behavior |
|---------|----------|
| `auto_commit: true` | Auto-commit on save (default) |
| `auto_commit: false` | File save only, manual commit required |

> **Note**: Auto-commit only commits to the local repository. It does NOT push to remote.

## Branch Configuration

### Target Branch

The commit target branch is determined by the `branch` setting in `bkstg.yaml`:

```yaml
sources:
  - type: github
    owner: your-org
    repo: your-catalog
    branch: main        # ← Commits go to this branch
    name: my-catalog
```

- **Default**: `main`
- This branch is checked out when cloning
- All local commits are made to this branch

### Multi-Environment Setup

For different branches in dev/prod environments:

```yaml
# Development
sources:
  - type: github
    branch: develop
    # ...

# Production
sources:
  - type: github
    branch: main
    # ...
```

## Sync Panel

### Sync States

The sync panel displays the status of each source:

| Display | State | Meaning |
|---------|-------|---------|
| `[OK]` | SYNCED | Local and remote are in sync |
| `[>>]` | LOCAL_AHEAD | Local has commits waiting to be pushed |
| `[<<]` | REMOTE_AHEAD | Remote has new changes |
| `[<>]` | DIVERGED | Local and remote have diverged |
| `[!!]` | CONFLICT | Conflict detected |
| `[--]` | NOT_CLONED | Not yet cloned |
| `[??]` | UNKNOWN | Unable to determine state |

### Action Buttons

Different buttons appear based on the state:

| State | Buttons Shown |
|-------|---------------|
| `[OK]` SYNCED | Sync (fetch latest) |
| `[>>]` LOCAL_AHEAD | **Push**, Create PR |
| `[<<]` REMOTE_AHEAD | Pull (fetch to local) |
| `[<>]` DIVERGED | Pull, **Create PR**, **Force Sync** |
| `[!!]` CONFLICT | **Force Sync** |

## Push vs Create PR

### Push (Direct Push)

- Pushes changes **directly** to the configured branch
- Changes are reflected on remote immediately without review
- Use for small changes or when review is not required

```
Local commit → Push directly to origin/main
```

### Create PR (Pull Request)

- Creates a new branch and opens a PR
- The PR targets the configured branch (e.g., main) as base
- Changes can be reviewed before merging

```
Local commit → Create new branch → Create PR (main ← new branch)
```

### Auto-Sync After Push

After a successful push, bkstg automatically syncs the local clone with the remote:

1. Push completes successfully
2. Local clone is automatically updated to match remote
3. State returns to `[OK]` SYNCED

This ensures your local state stays consistent with the remote repository.

## Force Sync

### When to Use Force Sync

Force Sync is used to recover from diverged or conflict states by discarding local changes:

- **DIVERGED state**: When both local and remote have different changes
- **CONFLICT state**: When conflicts cannot be automatically resolved
- **Recovery**: When you want to start fresh from the remote state

### What Force Sync Does

1. **Discards all local changes** - Uncommitted and committed local changes are lost
2. **Resets to remote** - Local branch is reset to match the remote branch exactly
3. **Re-clones if necessary** - In severe cases, may re-clone the repository

> **Warning**: Force Sync is destructive. All local changes will be permanently lost. Make sure to back up any important changes before using this feature.

### UI Steps

1. Open the **Sync Panel**
2. Find the source showing `[<>]` DIVERGED or `[!!]` CONFLICT
3. Click the **Force Sync** button
4. Confirm the action when prompted
5. Wait for the sync to complete

## Location (Team Repository) Sync

Team repositories referenced via Location entities can also be synced:

- Displayed with `[Location]` tag in the Sync panel
- Pull/Push/Create PR/Force Sync operations available
- Each team repository is managed independently

### Location Sync Features

| Feature | Description |
|---------|-------------|
| Independent sync | Each location repo has its own sync state |
| Sparse checkout | Only catalog files are cloned (efficient) |
| Full editing | Entities from locations are fully editable |
| PR support | Can create PRs to team repositories |

## Workflow Examples

### Simple Workflow (Direct Push)

1. Edit entity in UI and save
2. Changes are auto-committed locally
3. Click "Push" button in Sync panel
4. Changes are reflected on remote (auto-sync updates local)

### Review Workflow (Pull Request)

1. Edit entity in UI and save
2. Changes are auto-committed locally
3. Click "Create PR" button in Sync panel
4. Enter PR title and description
5. PR is created, merge after review
6. Pull to update local after merge

### Recovery Workflow (Force Sync)

When you're in a DIVERGED state and want to discard local changes:

1. Open Sync panel (shows `[<>]` DIVERGED)
2. Click "Force Sync" button
3. Confirm the action
4. Local is reset to match remote
5. State returns to `[OK]` SYNCED

### Manual PR Creation

To create a PR manually:

```bash
cd ~/.bkstg-clones/{owner}_{repo}_{branch}
git checkout -b feature/my-changes
git push -u origin feature/my-changes
gh pr create --base main --title "My changes" --body "Description"
```

## Clone Directory Structure

bkstg clones repositories to `~/.bkstg-clones/`:

```
~/.bkstg-clones/
├── {owner}_{repo}_{branch}/           # Main catalog repo
│   └── catalogs/
│       ├── components/
│       ├── apis/
│       └── scorecards/
├── {owner}_{repo}_{branch}_loc1/      # Location repo 1
│   └── catalogs/
└── {owner}_{repo}_{branch}_loc2/      # Location repo 2
    └── catalogs/
```

### Sparse Checkout

Repositories are cloned with sparse checkout enabled:

- Only the specified catalog directory is checked out
- Reduces disk usage and clone time
- Full repository history is still available

## Troubleshooting

### Shows "0 commit(s) to push" but `[>>]` state

- There may be uncommitted changes
- Click "Refresh" button to update the state

### Conflict Occurred

1. Try "Pull" to fetch the latest
2. If unresolvable, use "Force Sync" to reset to remote
3. Alternatively, use "Create PR" to create a PR and resolve conflicts on GitHub

### Changes Not Reflected

1. Click "Refresh" button in Sync panel
2. Click "Reload" at the bottom of the app to reload the catalog

### DIVERGED State Won't Resolve

If Pull doesn't resolve the diverged state:

1. Use "Create PR" to preserve your changes and merge via GitHub
2. Or use "Force Sync" to discard local changes and reset to remote

### Authentication Issues

bkstg uses `gh` CLI or `git` for GitHub operations:

- Ensure `gh auth login` has been completed
- Or ensure git credentials are configured
- Check that you have write access to the repository

---

*This guide is based on bkstg's current functionality (as of January 2026).*
