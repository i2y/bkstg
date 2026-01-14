# bkstg Scorecard Operations Guide

This guide provides a comprehensive explanation of bkstg's scorecard functionality, from UI operations to GitHub data structures.

---

## Table of Contents

1. [Scorecard System Overview](#1-scorecard-system-overview)
2. [File Structure and Data Flow](#2-file-structure-and-data-flow)
3. [Creating and Managing Scorecard Definitions](#3-creating-and-managing-scorecard-definitions)
4. [Assigning Scores to Entities](#4-assigning-scores-to-entities)
5. [Dashboard Analysis](#5-dashboard-analysis)
6. [History Tracking](#6-history-tracking)
7. [Operation Scenarios](#7-operation-scenarios)
8. [Best Practices](#8-best-practices)

---

## 1. Scorecard System Overview

### 1.1 What is a Scorecard?

A scorecard is a framework for quantitatively evaluating entities (Components, APIs, Resources, etc.) within your organization.

**Key Components:**

| Element | Description | Example |
|---------|-------------|---------|
| **Scorecard** | Major category of evaluation | `tech-health`, `security-audit` |
| **Score Definition** | Individual evaluation criteria | `test-coverage`, `doc-quality` |
| **Rank Definition** | Aggregated overall rating | `overall-health` (S/A/B/C/D) |

### 1.2 Evaluation Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Create         │ ──▶ │  Assign scores  │ ──▶ │  Analyze and    │
│  scorecard def  │     │  to entities    │     │  compare        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     (Settings)             (Entity Edit)           (Dashboard)
```

---

## 2. File Structure and Data Flow

### 2.1 GitHub File Structure

All bkstg data is stored as YAML files in GitHub repositories.

```
your-catalog-repo/
├── catalogs/
│   ├── components/          # Component entities
│   │   └── user-service.yaml
│   ├── apis/                # API entities
│   │   └── rest-api.yaml
│   ├── scorecards/          # Scorecard definitions ★
│   │   ├── tech-health.yaml
│   │   └── security-audit.yaml
│   ├── history/             # History data ★
│   │   ├── scores/          # Score change history
│   │   ├── ranks/           # Rank change history
│   │   └── definitions/     # Definition history
│   └── locations/           # External repository references
└── bkstg.yaml               # App configuration
```

### 2.2 Scorecard Definition File Structure

**File location**: `catalogs/scorecards/{scorecard-id}.yaml`

```yaml
# catalogs/scorecards/tech-health.yaml
id: tech-health
name: Technical Health
description: Evaluate technical health of the codebase

score_definitions:
  - id: test-coverage
    name: Test Coverage
    description: Unit test coverage percentage
    target_kinds:
      - Component
      - API
    min_value: 0
    max_value: 100

  - id: doc-quality
    name: Documentation Quality
    description: Completeness of README and API docs
    target_kinds:
      - Component
      - API
    min_value: 0
    max_value: 100

rank_definitions:
  - id: overall-health
    name: Overall Health
    description: Weighted aggregate of all scores
    target_kinds:
      - Component
      - API
    formula: (test_coverage * 0.6) + (doc_quality * 0.4)
    score_refs:
      - score_id: test-coverage
        variable_name: test_coverage
      - score_id: doc-quality
        variable_name: doc_quality
    thresholds:
      - label: S
        min_value: 90
      - label: A
        min_value: 80
      - label: B
        min_value: 60
      - label: C
        min_value: 40
      - label: D
        min_value: 0
```

### 2.3 Entity Score Data Structure

**File location**: `catalogs/components/{entity-name}.yaml`, etc.

```yaml
# catalogs/components/user-service.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: user-service
  title: User Service
  description: User authentication and management service
  tags:
    - backend
    - auth
  scores:                    # ★ Score data
    - score_id: test-coverage
      scorecard_id: tech-health
      value: 85
      reason: "Coverage measured in CI/CD"
    - score_id: doc-quality
      scorecard_id: tech-health
      value: 70
      reason: "API docs need improvement"
spec:
  type: service
  lifecycle: production
  owner: user:default/team-a
```

### 2.4 Overall Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                        GitHub Repository                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  catalogs/scorecards/*.yaml  ◀──────┐                            │
│         │                           │                            │
│         │ Load definitions          │ Push/PR from               │
│         ▼                           │ Settings                   │
│  ┌─────────────┐                    │                            │
│  │   bkstg     │ ────────────────────┘                           │
│  │   (App)     │                                                  │
│  └─────────────┘                                                  │
│         │                                                         │
│         │ Update scores                                           │
│         ▼                                                         │
│  catalogs/components/*.yaml  ◀──────┐                            │
│  catalogs/apis/*.yaml               │                            │
│         │                           │ Push/PR from               │
│         │ Load entities             │ Entity Editor              │
│         ▼                           │                            │
│  ┌─────────────┐                    │                            │
│  │   bkstg     │ ────────────────────┘                           │
│  │   (App)     │                                                  │
│  └─────────────┘                                                  │
│         │                                                         │
│         │ Record history                                          │
│         ▼                                                         │
│  catalogs/history/scores/*.yaml                                   │
│  catalogs/history/ranks/*.yaml                                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Creating and Managing Scorecard Definitions

### 3.1 Creating a New Scorecard

**UI Steps:**

1. Open **Settings** (left sidebar)
2. Select the **Scorecard** tab
3. Click **"+ New Scorecard"** button
4. Enter basic information:
   - **ID**: Unique identifier (e.g., `security-audit`)
   - **Name**: Display name (e.g., `Security Audit`)
   - **Description**: Description text

5. Add **Score Definitions**:
   - Click "+ Add Score"
   - Configure each item:
     - ID, name, description
     - Target Kinds (Component, API, etc.)
     - Min/Max values

6. Add **Rank Definitions**:
   - Click "+ Add Rank"
   - Set formula and thresholds

7. Click **Save**
8. In **Sync Panel**, execute **Push** or **Create PR**

### 3.2 Editing Scorecard Definitions

**UI Steps:**

1. **Settings** → **Scorecard** tab
2. Select the scorecard to edit
3. Edit each field
4. **Save** → **Push/PR**

### 3.3 Writing Rank Formulas

In the `formula` field of rank definitions, write expressions using score variable names.

**Available operators:**
- Arithmetic: `+`, `-`, `*`, `/`
- Comparison: `<`, `>`, `<=`, `>=`, `==`
- Logical: `and`, `or`, `not`
- Conditional: `if`/`else`
- Math functions: `min()`, `max()`, `abs()`

**Examples:**

```yaml
# Weighted average
formula: (test_coverage * 0.6) + (doc_quality * 0.4)

# Take minimum
formula: min(security_score, reliability_score)

# Conditional
formula: security_score if security_score < 50 else (security_score + reliability_score) / 2
```

### 3.4 Verifying Changes on GitHub

When you save and push a scorecard definition, the following file is updated:

```
catalogs/scorecards/{scorecard-id}.yaml
```

If you create a PR, changes are applied after review and merge.

---

## 4. Assigning Scores to Entities

### 4.1 Editing Scores for a Single Entity

**UI Steps:**

1. Select the target entity in **Catalog**
2. Click the **Edit** button
3. Select the **Scores** tab
4. Enter scores for each scorecard:
   - Select a scorecard
   - Enter values for each score definition
   - Add reason (optional)
5. Click **Save**
6. In **Sync Panel**, execute **Push** or **Create PR**

### 4.2 Notes on Score Entry

- **Target Kind**: Only entities included in `target_kinds` can have scores entered
- **Value range**: Must be within `min_value` to `max_value`
- **Empty values**: Scores without values are excluded from rank calculations

### 4.3 Verifying Changes on GitHub

When you save and push entity scores, the `metadata.scores` section of the entity's YAML file is updated:

```yaml
# Updated entity file
metadata:
  name: user-service
  scores:
    - score_id: test-coverage
      scorecard_id: tech-health
      value: 85
      reason: "Measured in CI/CD"
    - score_id: security-score
      scorecard_id: security-audit    # Score for new scorecard
      value: 90
      reason: "Passed vulnerability scan"
```

---

## 5. Dashboard Analysis

### 5.1 Scorecard Selection

Each dashboard tab displays a **scorecard selector**.

```
┌─────────────────────────────────────────────────────────┐
│ [All] [tech-health ✓] [security-audit] [team-standards] │
└─────────────────────────────────────────────────────────┘
```

- **All**: Aggregate data from all scorecards
- **Individual selection**: Filter by specific scorecard

### 5.2 Tab Functions

| Tab | Function | Scorecard Support |
|-----|----------|-------------------|
| **Overview** | Summary statistics (avg score, rank distribution, etc.) | ✅ Filterable |
| **Charts** | Bar charts and pie charts | ✅ Filterable |
| **Heatmaps** | Kind × Score heatmaps | ✅ Filterable |
| **Groups** | Group hierarchy with member ranks | ✅ Filterable |
| **History** | Score/rank change history | ✅ Filterable |
| **Leaderboard** | Entity list by rank | ✅ Filterable |
| **Scores** | All scores table | ✅ Filterable |
| **Compare** | Compare between scorecards | ✅ Select 2 to compare |

### 5.3 Using the Compare Tab

**UI Steps:**

1. **Dashboard** → **Compare** tab
2. Select **Scorecard A** from the left dropdown
3. Select **Scorecard B** from the right dropdown
4. Display contents:
   - **Top**: Rank distribution for each scorecard (pie charts)
   - **Bottom**: Per-entity comparison table

**Reading the Comparison Table:**

| Entity | Rank (SC-A) | Rank (SC-B) | Change |
|--------|-------------|-------------|--------|
| user-service | A (85) | B (72) | ↓ |
| api-gateway | B (70) | A (88) | ↑ |

- **↑**: Scorecard B has higher rank
- **↓**: Scorecard A has higher rank
- **-**: Same rank

### 5.4 Using the History Tab

**View Modes:**

1. **Recent Changes**: Recent score/rank change list
2. **By Score**: Time-series graph per score definition
3. **By Rank**: Time-series graph per rank definition

**Filtering by Scorecard:**
- When you select a scorecard, only score/rank definitions belonging to that scorecard are displayed

---

## 6. History Tracking

### 6.1 History Data Location

History data is automatically saved in the following locations:

```
catalogs/history/
├── scores/
│   └── {entity-id}/
│       └── {score-id}.yaml      # Score change history
├── ranks/
│   └── {entity-id}/
│       └── {rank-id}.yaml       # Rank change history
└── definitions/
    └── {scorecard-id}/
        ├── scores/
        │   └── {score-id}.yaml  # Score definition change history
        └── ranks/
            └── {rank-id}.yaml   # Rank definition change history
```

### 6.2 History File Contents

**Score history example:**

```yaml
# catalogs/history/scores/user-service/test-coverage.yaml
entity_id: component:default/user-service
score_id: test-coverage
scorecard_id: tech-health
history:
  - timestamp: "2024-01-15T10:30:00Z"
    value: 75
    reason: "Initial evaluation"
  - timestamp: "2024-02-01T14:20:00Z"
    value: 85
    reason: "After adding tests"
```

### 6.3 Using History Data

- **Trend analysis**: Check score trends with time-series graphs
- **Measure improvement**: Compare scores before and after initiatives
- **Audit support**: Use as evidence of evaluation history

---

## 7. Operation Scenarios

### 7.1 Adding a New Scorecard

**Scenario**: Introduce a new scorecard for security audits

1. **Settings** → **Scorecard** → **+ New Scorecard**
2. Enter basic info:
   - ID: `security-audit-v1`
   - Name: `Security Audit v1`
3. Add score definitions (e.g., `vulnerability-scan`, `access-control`)
4. Add rank definitions (set formula and thresholds)
5. **Save** → **Push/PR**

**Result on GitHub:**
```
catalogs/scorecards/security-audit-v1.yaml  # Created
```

### 7.2 Upgrading a Scorecard Version

**Scenario**: Major revision of evaluation criteria for an existing scorecard

**Recommended approach**: Create a new version as a separate scorecard

1. Create a new scorecard (ID: `tech-health-v2`)
2. Keep the old version (`tech-health-v1`)
3. Use **Compare** tab to compare v1 and v2
4. Delete the old version after transition period

**Benefits:**
- Can compare old and new criteria
- Enables gradual migration
- History data is preserved

### 7.3 Regular Scoring Operations

**Example Monthly Evaluation Flow:**

```
Week 1: Each team updates entity scores
         ↓
       Entity Editor → Scores tab → Enter values → Save → Create PR
         ↓
Week 2: Review and merge
         ↓
       Review PRs on GitHub → Merge
         ↓
Week 3: Analyze and report via dashboard
         ↓
       Dashboard → Analyze in each tab → Create report
         ↓
Week 4: Plan improvements
         ↓
       Create improvement plans for low-score entities
```

### 7.4 Team-based Operations

**Distributed Management Using Location Feature:**

```
Central Repository (bkstg-central)
├── catalogs/
│   ├── scorecards/           # Scorecard definitions managed centrally
│   └── locations/
│       ├── team-a.yaml       # Reference to Team A's repo
│       └── team-b.yaml       # Reference to Team B's repo

Team A Repository (team-a-catalog)
├── catalogs/
│   └── components/
│       └── service-a.yaml    # Entities managed by Team A
                              # (scores are stored here)

Team B Repository (team-b-catalog)
├── catalogs/
│   └── components/
│       └── service-b.yaml    # Entities managed by Team B
```

**Key Points:**
- Scorecard definitions are centrally managed in the central repository
- Each team updates scores in their own repository
- Dashboard analyzes data across all teams

---

## 8. Best Practices

### 8.1 Scorecard Design

| Recommendation | Description |
|----------------|-------------|
| **Clarify purpose** | Define what to measure and how to use it |
| **5-7 scores per scorecard** | Too many becomes hard to manage |
| **Agree on thresholds** | Get team consensus on S/A/B/C/D criteria |
| **Review periodically** | Adjust criteria as organization matures |

### 8.2 Scoring Operations

| Recommendation | Description |
|----------------|-------------|
| **Always include reason** | Document why you gave that value |
| **Update regularly** | Monthly or quarterly evaluations |
| **Consider automation** | Integrate with CI/CD for automated scoring |
| **Review via PR** | Review score changes through PRs |

### 8.3 Dashboard Usage

| Recommendation | Description |
|----------------|-------------|
| **Share in meetings** | Display dashboard in regular meetings |
| **Compare perspectives** | Analyze from multiple scorecard viewpoints |
| **Track with History** | Verify improvement effects via history |
| **Celebrate with Leaderboard** | Recognize high-scoring teams |

### 8.4 Troubleshooting

| Issue | Solution |
|-------|----------|
| Rank not calculated | Check if `score_refs` are correct |
| Score not displayed | Verify entity Kind is in `target_kinds` |
| History not updated | Pull latest data from Sync panel |
| No data in Compare tab | Need entities evaluated in both scorecards |

---

## Appendix: Quick Reference

### UI Operation Reference

| Operation | Location | Steps |
|-----------|----------|-------|
| Create scorecard | Settings → Scorecard | + New Scorecard → Enter → Save → Push |
| Enter scores | Catalog → Entity → Edit | Scores tab → Enter values → Save → Push |
| View dashboard | Dashboard | Select tab → Select scorecard |
| Compare scorecards | Dashboard → Compare | Select 2 scorecards |
| View history | Dashboard → History | Select mode → Select scorecard |

### File Location Reference

| Data | File Path |
|------|-----------|
| Scorecard definition | `catalogs/scorecards/{id}.yaml` |
| Entity scores | `catalogs/{kind}s/{name}.yaml` in `metadata.scores` |
| Score history | `catalogs/history/scores/{entity}/{score}.yaml` |
| Rank history | `catalogs/history/ranks/{entity}/{rank}.yaml` |

---

*This guide is based on bkstg's current functionality (as of January 2026).*
