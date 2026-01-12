# Release Procedure

Steps to release a new version of bkstg.

## Prerequisites

- `gh` CLI installed
- `uv` installed
- Push access to GitHub repositories

## Steps

### 1. Update Version

Update version in `pyproject.toml`:

```toml
version = "X.Y.Z"
```

### 2. Update Dependencies (if needed)

```bash
uv lock --refresh
uv sync
```

### 3. Build DMG

```bash
rm -rf dist
uv run ux bundle --format app --dmg
```

### 4. Get SHA256

```bash
shasum -a 256 dist/bkstg.dmg
```

### 5. Commit, Tag, and Push

```bash
git add pyproject.toml uv.lock
git commit -m "Bump version to X.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

### 6. Create GitHub Release

```bash
gh release create vX.Y.Z dist/bkstg.dmg --title "vX.Y.Z" --notes "## Changes
- Describe changes here"
```

### 7. Update Homebrew Cask

```bash
cd /tmp
rm -rf homebrew-tap
gh repo clone i2y/homebrew-tap
cd homebrew-tap
```

Edit `Casks/bkstg.rb`:
- Update `version` to new version
- Update `sha256` to value from step 4

```bash
git add Casks/bkstg.rb
git commit -m "Update bkstg to vX.Y.Z"
git push
```

## Verification

```bash
brew upgrade i2y/tap/bkstg
```
