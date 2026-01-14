# bkstg スコアカード運用ガイド

このガイドでは、bkstgのスコアカード機能について、UI操作方法からGitHub上のデータ構造まで包括的に解説します。

---

## 目次

1. [スコアカードシステム概要](#1-スコアカードシステム概要)
2. [ファイル構造とデータフロー](#2-ファイル構造とデータフロー)
3. [スコアカード定義の作成・管理](#3-スコアカード定義の作成管理)
4. [エンティティへのスコア付与](#4-エンティティへのスコア付与)
5. [ダッシュボードでの分析](#5-ダッシュボードでの分析)
6. [履歴追跡機能](#6-履歴追跡機能)
7. [運用シナリオ別ガイド](#7-運用シナリオ別ガイド)
8. [ベストプラクティス](#8-ベストプラクティス)

---

## 1. スコアカードシステム概要

### 1.1 スコアカードとは

スコアカードは、組織内のエンティティ（Component、API、Resource等）を定量的に評価するためのフレームワークです。

**主な構成要素：**

| 要素 | 説明 | 例 |
|------|------|-----|
| **スコアカード** | 評価の大分類 | `tech-health`、`security-audit` |
| **スコア定義** | 個別の評価項目 | `test-coverage`、`doc-quality` |
| **ランク定義** | スコアを集約した総合評価 | `overall-health` (S/A/B/C/D) |

### 1.2 評価の流れ

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  スコアカード定義  │ ──▶ │  エンティティに   │ ──▶ │  ダッシュボードで │
│  を作成          │     │  スコア付与       │     │  分析・比較      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     (Settings)             (Entity Edit)           (Dashboard)
```

---

## 2. ファイル構造とデータフロー

### 2.1 GitHub上のファイル構成

bkstgのデータはすべてYAMLファイルとしてGitHubリポジトリに保存されます。

```
your-catalog-repo/
├── catalogs/
│   ├── components/          # Componentエンティティ
│   │   └── user-service.yaml
│   ├── apis/                # APIエンティティ
│   │   └── rest-api.yaml
│   ├── scorecards/          # スコアカード定義 ★
│   │   ├── tech-health.yaml
│   │   └── security-audit.yaml
│   ├── history/             # 履歴データ ★
│   │   ├── scores/          # スコア変更履歴
│   │   ├── ranks/           # ランク変更履歴
│   │   └── definitions/     # 定義履歴
│   └── locations/           # 外部リポジトリ参照
└── bkstg.yaml               # アプリ設定
```

### 2.2 スコアカード定義ファイルの構造

**ファイル場所**: `catalogs/scorecards/{scorecard-id}.yaml`

```yaml
# catalogs/scorecards/tech-health.yaml
id: tech-health
name: Technical Health
description: コードベースの技術的健全性を評価

score_definitions:
  - id: test-coverage
    name: テストカバレッジ
    description: ユニットテストのカバレッジ率
    target_kinds:
      - Component
      - API
    min_value: 0
    max_value: 100

  - id: doc-quality
    name: ドキュメント品質
    description: READMEとAPIドキュメントの充実度
    target_kinds:
      - Component
      - API
    min_value: 0
    max_value: 100

rank_definitions:
  - id: overall-health
    name: 総合健全性
    description: 各スコアを重み付けした総合評価
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

### 2.3 エンティティのスコアデータ構造

**ファイル場所**: `catalogs/components/{entity-name}.yaml` など

```yaml
# catalogs/components/user-service.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: user-service
  title: User Service
  description: ユーザー認証・管理サービス
  tags:
    - backend
    - auth
  scores:                    # ★ スコアデータ
    - score_id: test-coverage
      scorecard_id: tech-health
      value: 85
      reason: "CI/CDでカバレッジ計測済み"
    - score_id: doc-quality
      scorecard_id: tech-health
      value: 70
      reason: "APIドキュメント要改善"
spec:
  type: service
  lifecycle: production
  owner: user:default/team-a
```

### 2.4 データフローの全体像

```
┌──────────────────────────────────────────────────────────────────┐
│                        GitHub Repository                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  catalogs/scorecards/*.yaml  ◀──────┐                            │
│         │                           │                            │
│         │ 定義読み込み               │ Settings で                │
│         ▼                           │ Push/PR 作成              │
│  ┌─────────────┐                    │                            │
│  │   bkstg     │ ────────────────────┘                           │
│  │   (App)     │                                                  │
│  └─────────────┘                                                  │
│         │                                                         │
│         │ スコア更新                                               │
│         ▼                                                         │
│  catalogs/components/*.yaml  ◀──────┐                            │
│  catalogs/apis/*.yaml               │                            │
│         │                           │ Entity Editor で           │
│         │ エンティティ読み込み        │ Push/PR 作成              │
│         ▼                           │                            │
│  ┌─────────────┐                    │                            │
│  │   bkstg     │ ────────────────────┘                           │
│  │   (App)     │                                                  │
│  └─────────────┘                                                  │
│         │                                                         │
│         │ 履歴記録                                                 │
│         ▼                                                         │
│  catalogs/history/scores/*.yaml                                   │
│  catalogs/history/ranks/*.yaml                                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. スコアカード定義の作成・管理

### 3.1 新規スコアカードの作成

**UI操作手順：**

1. **Settings** を開く（左サイドバー）
2. **Scorecard** タブを選択
3. **「+ New Scorecard」** ボタンをクリック
4. 基本情報を入力：
   - **ID**: 一意の識別子（例: `security-audit`）
   - **Name**: 表示名（例: `Security Audit`）
   - **Description**: 説明文

5. **Score Definitions** を追加：
   - 「+ Add Score」をクリック
   - 各項目を設定：
     - ID、名前、説明
     - 対象Kind（Component、API等）
     - 最小値/最大値

6. **Rank Definitions** を追加：
   - 「+ Add Rank」をクリック
   - 計算式と閾値を設定

7. **Save** をクリック
8. **Sync Panel** で **Push** または **Create PR** を実行

### 3.2 スコアカード定義の編集

**UI操作手順：**

1. **Settings** → **Scorecard** タブ
2. 編集したいスコアカードを選択
3. 各フィールドを編集
4. **Save** → **Push/PR**

### 3.3 ランク計算式の書き方

ランク定義の `formula` フィールドでは、参照スコアの変数名を使った数式を記述します。

**使用可能な演算子：**
- 四則演算: `+`, `-`, `*`, `/`
- 比較: `<`, `>`, `<=`, `>=`, `==`
- 論理: `and`, `or`, `not`
- 条件: `if`/`else`
- 数学関数: `min()`, `max()`, `abs()`

**例：**

```yaml
# 重み付け平均
formula: (test_coverage * 0.6) + (doc_quality * 0.4)

# 最小値採用
formula: min(security_score, reliability_score)

# 条件分岐
formula: security_score if security_score < 50 else (security_score + reliability_score) / 2
```

### 3.4 GitHub上での変更確認

スコアカード定義を保存・Pushすると、以下のファイルが更新されます：

```
catalogs/scorecards/{scorecard-id}.yaml
```

PRを作成した場合は、レビュー後にマージすることで変更が反映されます。

---

## 4. エンティティへのスコア付与

### 4.1 単一エンティティのスコア編集

**UI操作手順：**

1. **Catalog** で対象エンティティを選択
2. **Edit** ボタンをクリック
3. **Scores** タブを選択
4. スコアカードごとにスコアを入力：
   - スコアカードを選択
   - 各スコア定義の値を入力
   - 理由（reason）を記載（任意）
5. **Save** をクリック
6. **Sync Panel** で **Push** または **Create PR**

### 4.2 スコア入力時の注意点

- **対象Kind**: スコア定義の `target_kinds` に含まれるエンティティのみ入力可能
- **値の範囲**: `min_value` ～ `max_value` の範囲内
- **未入力**: 未入力のスコアはランク計算から除外される

### 4.3 GitHub上での変更確認

エンティティのスコアを保存・Pushすると、該当エンティティのYAMLファイルの `metadata.scores` セクションが更新されます：

```yaml
# 更新後のエンティティファイル
metadata:
  name: user-service
  scores:
    - score_id: test-coverage
      scorecard_id: tech-health
      value: 85
      reason: "CI/CDで計測"
    - score_id: security-score
      scorecard_id: security-audit    # 新しいスコアカードのスコア
      value: 90
      reason: "脆弱性スキャン合格"
```

---

## 5. ダッシュボードでの分析

### 5.1 スコアカード選択機能

ダッシュボードの各タブには **スコアカードセレクタ** が表示されます。

```
┌─────────────────────────────────────────────────────────┐
│ [All] [tech-health ✓] [security-audit] [team-standards] │
└─────────────────────────────────────────────────────────┘
```

- **All**: 全スコアカードのデータを集約表示
- **個別選択**: 特定スコアカードでフィルタリング

### 5.2 各タブの機能

| タブ | 機能 | スコアカード対応 |
|------|------|------------------|
| **Overview** | サマリー統計（平均スコア、ランク分布等） | ✅ フィルタリング可 |
| **Charts** | 棒グラフ・円グラフによる可視化 | ✅ フィルタリング可 |
| **Heatmaps** | Kind×スコアのヒートマップ | ✅ フィルタリング可 |
| **Groups** | グループ階層とメンバーのランク表示 | ✅ フィルタリング可 |
| **History** | スコア/ランクの変更履歴 | ✅ フィルタリング可 |
| **Leaderboard** | ランク別エンティティ一覧 | ✅ フィルタリング可 |
| **Scores** | 全スコア一覧テーブル | ✅ フィルタリング可 |
| **Compare** | スコアカード間比較 | ✅ 2つ選択して比較 |

### 5.3 Compare（比較）タブの使い方

**UI操作手順：**

1. **Dashboard** → **Compare** タブ
2. 左側のドロップダウンで **スコアカードA** を選択
3. 右側のドロップダウンで **スコアカードB** を選択
4. 表示内容：
   - **上部**: 各スコアカードのランク分布（円グラフ）
   - **下部**: エンティティごとの比較テーブル

**比較テーブルの見方：**

| Entity | Rank (SC-A) | Rank (SC-B) | Change |
|--------|-------------|-------------|--------|
| user-service | A (85) | B (72) | ↓ |
| api-gateway | B (70) | A (88) | ↑ |

- **↑**: スコアカードBの方がランクが高い
- **↓**: スコアカードAの方がランクが高い
- **-**: 同じランク

### 5.4 History（履歴）タブの使い方

**表示モード：**

1. **Recent Changes**: 最近のスコア/ランク変更一覧
2. **By Score**: スコア定義ごとの時系列グラフ
3. **By Rank**: ランク定義ごとの時系列グラフ

**スコアカードでフィルタリング：**
- スコアカードを選択すると、そのスコアカードに属するスコア/ランク定義のみが表示されます

---

## 6. 履歴追跡機能

### 6.1 履歴データの保存場所

履歴データは以下の場所に自動保存されます：

```
catalogs/history/
├── scores/
│   └── {entity-id}/
│       └── {score-id}.yaml      # スコアの変更履歴
├── ranks/
│   └── {entity-id}/
│       └── {rank-id}.yaml       # ランクの変更履歴
└── definitions/
    └── {scorecard-id}/
        ├── scores/
        │   └── {score-id}.yaml  # スコア定義の変更履歴
        └── ranks/
            └── {rank-id}.yaml   # ランク定義の変更履歴
```

### 6.2 履歴ファイルの内容

**スコア履歴の例：**

```yaml
# catalogs/history/scores/user-service/test-coverage.yaml
entity_id: component:default/user-service
score_id: test-coverage
scorecard_id: tech-health
history:
  - timestamp: "2024-01-15T10:30:00Z"
    value: 75
    reason: "初回評価"
  - timestamp: "2024-02-01T14:20:00Z"
    value: 85
    reason: "テスト追加後"
```

### 6.3 履歴の活用

- **トレンド分析**: 時系列グラフでスコアの推移を確認
- **改善効果測定**: 施策実施前後のスコア比較
- **監査対応**: 評価履歴のエビデンスとして利用

---

## 7. 運用シナリオ別ガイド

### 7.1 新しいスコアカードを追加する場合

**シナリオ**: セキュリティ監査用の新しいスコアカードを導入

1. **Settings** → **Scorecard** → **+ New Scorecard**
2. 基本情報を入力：
   - ID: `security-audit-v1`
   - Name: `Security Audit v1`
3. スコア定義を追加（例: `vulnerability-scan`, `access-control`）
4. ランク定義を追加（計算式と閾値を設定）
5. **Save** → **Push/PR**

**GitHub上の結果：**
```
catalogs/scorecards/security-audit-v1.yaml  # 新規作成
```

### 7.2 スコアカードのバージョンアップ

**シナリオ**: 既存スコアカードの評価基準を大幅改訂

**推奨アプローチ**: 新バージョンとして別スコアカードを作成

1. 新しいスコアカードを作成（ID: `tech-health-v2`）
2. 旧バージョン（`tech-health-v1`）は残しておく
3. **Compare** タブで v1 と v2 を比較可能
4. 移行期間後、旧バージョンを削除

**メリット：**
- 旧基準と新基準の比較が可能
- 段階的な移行が可能
- 履歴データが保持される

### 7.3 定期的なスコアリング運用

**月次評価フロー例：**

```
1週目: 各チームがエンティティのスコアを更新
         ↓
       Entity Editor → Scores タブ → 値入力 → Save → PR作成
         ↓
2週目: レビュー・マージ
         ↓
       GitHub上でPRレビュー → マージ
         ↓
3週目: ダッシュボードで分析・報告
         ↓
       Dashboard → 各タブで分析 → レポート作成
         ↓
4週目: 改善施策の検討
         ↓
       低スコアエンティティの改善計画
```

### 7.4 チーム別の運用

**Location機能を使った分散管理：**

```
中央リポジトリ (bkstg-central)
├── catalogs/
│   ├── scorecards/           # スコアカード定義は中央で管理
│   └── locations/
│       ├── team-a.yaml       # Team Aのリポジトリを参照
│       └── team-b.yaml       # Team Bのリポジトリを参照

Team Aリポジトリ (team-a-catalog)
├── catalogs/
│   └── components/
│       └── service-a.yaml    # Team Aが管理するエンティティ
                              # (スコアもここに記載)

Team Bリポジトリ (team-b-catalog)
├── catalogs/
│   └── components/
│       └── service-b.yaml    # Team Bが管理するエンティティ
```

**運用ポイント：**
- スコアカード定義は中央リポジトリで一元管理
- 各チームは自分のリポジトリでスコアを更新
- ダッシュボードでは全チームのデータを横断的に分析

---

## 8. ベストプラクティス

### 8.1 スコアカード設計

| 推奨事項 | 説明 |
|---------|------|
| **目的を明確に** | 何を測定し、どう活用するかを明確化 |
| **スコアは5-7個程度** | 多すぎると管理が煩雑に |
| **閾値は合意の上で** | S/A/B/C/Dの基準はチームで合意 |
| **定期的に見直し** | 組織の成熟度に合わせて基準を調整 |

### 8.2 スコアリング運用

| 推奨事項 | 説明 |
|---------|------|
| **reasonを必ず記載** | なぜその値かの根拠を残す |
| **定期的に更新** | 月次や四半期での定期評価 |
| **自動化を検討** | CI/CDと連携した自動スコアリング |
| **PRでレビュー** | スコア変更はPRを通じてレビュー |

### 8.3 ダッシュボード活用

| 推奨事項 | 説明 |
|---------|------|
| **定例会議で共有** | ダッシュボードを定例会議で表示 |
| **Compareで比較** | 複数スコアカードの視点で分析 |
| **Historyで追跡** | 改善施策の効果を履歴で確認 |
| **Leaderboardで表彰** | 高スコアチームを称える |

### 8.4 トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| ランクが計算されない | スコア定義の `score_refs` が正しいか確認 |
| スコアが表示されない | `target_kinds` にエンティティのKindが含まれているか確認 |
| 履歴が反映されない | Syncパネルで最新データをPull |
| 比較タブでデータがない | 両方のスコアカードで評価済みのエンティティが必要 |

---

## 付録: クイックリファレンス

### UI操作早見表

| 操作 | 場所 | 手順 |
|------|------|------|
| スコアカード作成 | Settings → Scorecard | + New Scorecard → 入力 → Save → Push |
| スコア入力 | Catalog → Entity → Edit | Scores タブ → 値入力 → Save → Push |
| ダッシュボード表示 | Dashboard | タブ選択 → スコアカード選択 |
| スコアカード比較 | Dashboard → Compare | 2つのスコアカードを選択 |
| 履歴確認 | Dashboard → History | モード選択 → スコアカード選択 |

### ファイル場所早見表

| データ | ファイルパス |
|--------|-------------|
| スコアカード定義 | `catalogs/scorecards/{id}.yaml` |
| エンティティスコア | `catalogs/{kind}s/{name}.yaml` の `metadata.scores` |
| スコア履歴 | `catalogs/history/scores/{entity}/{score}.yaml` |
| ランク履歴 | `catalogs/history/ranks/{entity}/{rank}.yaml` |

---

*このガイドは bkstg の現行機能（2026年1月時点）に基づいています。*
