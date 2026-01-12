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
| `[>>]` LOCAL_AHEAD | **Push** (push to remote) |
| `[<<]` REMOTE_AHEAD | Pull (fetch to local) |
| `[<>]` DIVERGED | Pull + **Create PR** |

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

### When Create PR Button Appears

In the current implementation, the **Create PR button** only appears when:

- State is `[<>]` DIVERGED (local and remote have diverged)

In `[>>]` LOCAL_AHEAD state, only the Push button is shown.

> **Tip**: If you always want to use PRs, you can create them manually via git CLI or GitHub UI instead of using the Push button.

## Workflow Examples

### Simple Workflow (Direct Push)

1. Edit entity in UI and save
2. Changes are auto-committed locally
3. Click "Push" button in Sync panel
4. Changes are reflected on remote

### Review Workflow

1. Edit entity in UI and save
2. Changes are auto-committed locally
3. Click "Create PR" button in Sync panel (when DIVERGED)
4. Enter PR title and description
5. PR is created, merge after review

### Manual PR Creation

To create a PR when in `[>>]` LOCAL_AHEAD state:

```bash
cd ~/.bkstg-clones/{owner}_{repo}_{branch}
git checkout -b feature/my-changes
git push -u origin feature/my-changes
gh pr create --base main --title "My changes" --body "Description"
```

## Location (Team Repository) Sync

Team repositories referenced via Location entities can also be synced:

- Displayed with `[Location]` tag in the Sync panel
- Pull/Push/Create PR operations available
- Each team repository is managed independently

## Troubleshooting

### Shows "0 commit(s) to push" but `[>>]` state

- There may be uncommitted changes
- Click "Refresh" button to update the state

### Conflict Occurred

1. Try "Pull" to fetch the latest
2. If unresolvable, use "Create PR" to create a PR
3. Resolve conflicts on GitHub and merge

### Changes Not Reflected

1. Click "Refresh" button in Sync panel
2. Click "Reload" at the bottom of the app to reload the catalog
