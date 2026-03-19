# GeoIP Enrichment Feature Implementation Plan

MaxMind GeoLite2 データベースを使用して `source_ip_address` フィールドをエンリッチする機能の実装計画。

---

## 1. 概要

`source_ip_address` フィールドをMaxMind GeoLite2データベースでジオロケーション情報に変換し、`cloudtrail_events` テーブルに7つのGeoカラムを追加する。`ingest` コマンドでのリアルタイムエンリッチと、既存DBへの後付け `enrich` サブコマンドの2経路で対応する。DuckDB Appender の列順序への影響、`READ_WRITE` 排他制御、TDDサイクルを厳守する。

---

## 2. テストリスト（実装前に全テストを列挙）

TDDの原則に従い、**実装前に全テストを確定**する。

### `geoip.rs` のテストリスト

| #    | テスト名                                    | 検証内容                                            |
|------|---------------------------------------------|----------------------------------------------------|
| G-01 | `test_classify_rfc1918_10_x`                | `10.0.0.1` → `"PRIVATE"`                          |
| G-02 | `test_classify_rfc1918_172_16_to_31`        | `172.16.0.1`, `172.31.255.255` → `"PRIVATE"`      |
| G-03 | `test_classify_rfc1918_192_168`             | `192.168.0.1` → `"PRIVATE"`                       |
| G-04 | `test_classify_loopback_ipv4`               | `127.0.0.1` → `"LOOPBACK"`                        |
| G-05 | `test_classify_loopback_ipv6`               | `::1` → `"LOOPBACK"`                              |
| G-06 | `test_classify_link_local_169_254`          | `169.254.1.1` → `"LINK-LOCAL"`                    |
| G-07 | `test_classify_link_local_ipv6_fe80`        | `fe80::1` → `"LINK-LOCAL"`                        |
| G-08 | `test_classify_special_broadcast`           | `255.255.255.255` → `"SPECIAL"`                   |
| G-09 | `test_classify_public_returns_none`         | `8.8.8.8` → `None`（mmdb参照が必要）              |
| G-10 | `test_parse_invalid_ip_string`              | `"not-an-ip"` → `Err(...)`                        |
| G-11 | `test_lookup_known_ip_city_db`              | テスト用mmdbで既知IP（`81.2.69.160`）→ `country_code="GB"` |
| G-12 | `test_lookup_ipv6_city_db`                  | IPv6アドレスのルックアップ成功                      |
| G-13 | `test_lookup_ip_not_in_database`            | DBに存在しないIPはエラーなくNoneを返す              |
| G-14 | `test_enricher_with_city_only`              | ASN DBなしでも動作する                             |
| G-15 | `test_enricher_city_and_asn`                | 両DB提供時にASN/org情報も返す                      |
| G-16 | `test_enricher_private_ip_skips_mmdb_access`| プライベートIPはmmdbを参照せず即時返却             |
| G-17 | `test_enricher_none_returns_all_none`       | enricherなし（`None`）は全フィールドNone           |

### `db.rs` 追加テストリスト

| #    | テスト名                                        | 検証内容                                            |
|------|------------------------------------------------|----------------------------------------------------|
| D-01 | `test_ensure_geo_columns_adds_seven_columns`    | `ALTER TABLE` 後に7カラム存在                      |
| D-02 | `test_ensure_geo_columns_is_idempotent`         | 2回呼び出しでもエラーなし                           |
| D-03 | `test_insert_events_with_geo_populates_columns` | GeoInfo提供時にDB値が正しい                         |
| D-04 | `test_insert_events_without_geo_columns_are_null` | enricherなし時にgeoカラムがNULL                  |
| D-05 | `test_insert_events_private_ip_stores_marker`   | `"PRIVATE"`マーカーが書き込まれる                  |

### `enrich.rs` テストリスト

| #    | テスト名                                        | 検証内容                                            |
|------|------------------------------------------------|----------------------------------------------------|
| E-01 | `test_enrich_adds_geo_columns_to_existing_table`| 既存テーブルに7カラム追加                           |
| E-02 | `test_enrich_public_ip_writes_geo_data`         | パブリックIPのgeo情報がUPDATE                       |
| E-03 | `test_enrich_private_ip_writes_marker`          | `"PRIVATE"` マーカーが書き込まれる                 |
| E-04 | `test_enrich_skips_null_source_ip`              | source_ip_address=NULLの行はUPDATEされない         |
| E-05 | `test_enrich_is_idempotent`                     | 既エンリッチ済み行は上書きされない（WHERE IS NULL条件）|
| E-06 | `test_enrich_deduplicates_lookups`              | 同一IPは1回だけmmdb参照（パフォーマンス保証）       |
| E-07 | `test_enrich_returns_stats`                     | `EnrichStats { enriched_count, skipped_count, elapsed_secs }` |
| E-08 | `test_enrich_aws_service_ip_stored_as_special`  | `"AWS"` など非ルーティングIPの処理                 |

### `ingest.rs` 追加テストリスト

| #    | テスト名                                        | 検証内容                                            |
|------|------------------------------------------------|----------------------------------------------------|
| I-01 | `test_ingest_with_geoip_populates_geo_columns`  | `--geoip-city` 指定時にgeoカラムが埋まる            |
| I-02 | `test_ingest_without_geoip_geo_columns_are_null`| enricher未指定時にgeoカラムはNULL                  |

### CLIテストリスト（`cli_test.rs`）

| #    | テスト名                                        | 検証内容                                            |
|------|------------------------------------------------|----------------------------------------------------|
| C-01 | `test_cli_ingest_with_geoip_city_flag`          | `ingest --geoip-city <path>` が正常終了            |
| C-02 | `test_cli_enrich_command_succeeds`              | `enrich --db <path> --geoip-city <path>` が正常終了|
| C-03 | `test_cli_enrich_uses_geoip_city_env_var`       | `GEOIP_CITY_PATH` 環境変数が適用される             |
| C-04 | `test_cli_enrich_nonexistent_mmdb_shows_error`  | 存在しないmmdbパスでエラー終了                      |
| C-05 | `test_cli_enrich_prints_enriched_count`         | stdout に `enriched_count=N` が出力される           |

---

## 3. 実装フェーズ

各フェーズは **Red → Green → Refactor** のサイクルで進める。

---

### Phase 1: `geoip.rs` — GeoIPルックアップモジュール新規作成

**目的:** IPアドレスを受け取り `GeoInfo` を返す純粋な関数群を独立モジュールに分離する。

**新規作成:** `ingester/src/geoip.rs`

**Red:** まず G-01〜G-10 の特殊IP分類テストを記述（mmdb不要・失敗する）

**Green — 実装する構造体と関数:**

```rust
// ingester/src/geoip.rs

/// Geo-enrichment data derived from a MaxMind GeoLite2 lookup.
pub struct GeoInfo {
    pub country_code: Option<String>,  // e.g. "US", "JP", "PRIVATE"
    pub country_name: Option<String>,
    pub city:         Option<String>,
    pub latitude:     Option<f64>,
    pub longitude:    Option<f64>,
    pub asn:          Option<String>,  // e.g. "AS15169"
    pub org:          Option<String>,  // e.g. "Google LLC"
}

/// Configuration for opening GeoIP database files.
pub struct GeoipConfig {
    pub city_db_path: PathBuf,
    pub asn_db_path:  Option<PathBuf>,
}

/// Wraps maxminddb::Reader instances for City and (optionally) ASN databases.
pub struct GeoipEnricher { ... }

impl GeoipEnricher {
    /// Open GeoIP database files from the given config paths.
    pub fn open(config: &GeoipConfig) -> Result<Self> { ... }

    /// Look up GeoInfo for an IP address string.
    /// Returns GeoInfo with special markers for private/loopback/link-local IPs.
    /// Returns GeoInfo::all_none() for unrecognized non-IP strings (e.g. "AWS").
    pub fn lookup(&self, ip_str: &str) -> Result<GeoInfo> { ... }
}

/// Classify special-purpose IP addresses without a database lookup.
/// Returns Some("PRIVATE" | "LOOPBACK" | "LINK-LOCAL" | "SPECIAL") or None.
pub fn classify_special_ip(addr: IpAddr) -> Option<&'static str> { ... }
```

**Refactor:** `classify_special_ip` を `lookup()` 内部で事前呼び出しし、mmdb参照を最小化する。

---

### Phase 2: `db.rs` 拡張 — スキーママイグレーション + 24カラムAppender

**目的:** 既存テーブルに7つのGeoカラムを追加し、`insert_events` が `Option<GeoInfo>` を受け取れるようにする。

**変更:** `ingester/src/db.rs`

**Red:** D-01〜D-05 のテストを記述（失敗する）

**Green — 追加・変更する関数:**

```rust
// db.rs への追加

/// Add 7 geo-enrichment columns to `cloudtrail_events` if they do not exist.
/// Uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — safe to call repeatedly.
pub fn ensure_geo_columns(conn: &Connection) -> Result<()> {
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_code VARCHAR;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_name VARCHAR;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_city VARCHAR;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_latitude DOUBLE;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_longitude DOUBLE;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_asn VARCHAR;
    // ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_org VARCHAR;
}

/// Insert events with optional GeoInfo.
/// Appender writes 17 + 7 = 24 columns; geo fields are NULL when geoip is None.
pub fn insert_events_with_geo(
    conn: &Connection,
    events: &[CloudTrailEvent],
    geoip: Option<&GeoipEnricher>,
) -> Result<usize> { ... }
```

**重要な設計上の制約:**

- `duckdb::Appender` は列順に値を渡すため、`ensure_geo_columns` 呼び出し後はAppenderが **17列ではなく24列** を期待する。
- 既存の `insert_events` を `insert_events_with_geo(conn, events, None)` に移行する（後方互換ラッパーとして残すかdeprecateするか選択）。
- `ensure_table` を `ensure_table` + `ensure_geo_columns` の組み合わせに変更し、常に24カラムスキーマを保証する。

**Refactor:** `ensure_table()` の内部から `ensure_geo_columns()` を呼び出すよう統合し、常に24カラムスキーマが保証された状態を確立する。

---

### Phase 3: `ingest.rs` 拡張 — GeoIP enricherのパイプライン統合

**目的:** `ingest_core` に `Option<&GeoipEnricher>` を受け渡し、シリアル挿入フェーズでGeoIPルックアップを実行する。

**変更:** `ingester/src/ingest.rs`

**Red:** I-01〜I-02 のテストを記述（失敗する）

**Green:**

```rust
// ingest_core のシグネチャ変更
fn ingest_core(
    path: &Path,
    conn: &Connection,
    show_progress: bool,
    date_filter: &DateFilter,
    path_filter: &PathFilter,
    geoip: Option<&GeoipEnricher>,  // <- 追加
) -> Result<IngestStats>
```

シリアル挿入フェーズ（rayon並列解析後）でのみルックアップを実行する:

- **Parallelフェーズ:** ファイル読み込み → SHA-256 → JSON解析（変更なし）
- **Serialフェーズ:** `insert_events_with_geo(conn, &records, geoip)` に変更

新しいパブリック関数を追加:

```rust
pub fn ingest_with_geoip(
    path: &Path,
    conn: &Connection,
    show_progress: bool,
    date_filter: &DateFilter,
    path_filter: &PathFilter,
    geoip: &GeoipEnricher,
) -> Result<IngestStats>
```

`ingest_with_filters` はそのまま維持し（geoip=None）、後方互換を保つ。

**Refactor:** `ingest_core` の引数が増えるため、`IngestOptions` 構造体へのリファクタリングを検討（Phase 5完了後に判断）。

---

### Phase 4: `enrich.rs` — enrichサブコマンドロジック（新規作成）

**目的:** 既存DBのNULL geo行を後付けエンリッチするバッチ処理を独立モジュール化する。

**新規作成:** `ingester/src/enrich.rs`

**Red:** E-01〜E-08 のテストを記述（失敗する）

**Green — 実装するロジック:**

```rust
// enrich.rs

pub struct EnrichStats {
    pub enriched_count: usize,   // rows updated
    pub skipped_count:  usize,   // rows with NULL source_ip or non-IP value
    pub elapsed_secs:   f64,
}

pub fn enrich_existing(conn: &Connection, geoip: &GeoipEnricher) -> Result<EnrichStats> {
    // 1. ensure_geo_columns(conn) — ALTER TABLE IF NOT EXISTS
    // 2. SELECT DISTINCT source_ip_address FROM cloudtrail_events
    //    WHERE source_ip_address IS NOT NULL AND geo_country_code IS NULL
    // 3. For each unique IP: lookup(ip) -> GeoInfo
    // 4. UPDATE cloudtrail_events SET geo_country_code = ?, ...
    //    WHERE source_ip_address = ? AND geo_country_code IS NULL
    // 5. Return EnrichStats
}
```

**DuckDBのUPDATE方針:**

- `duckdb::Appender` はINSERT専用のため、UPDATEには `conn.execute()` を使用する（プロジェクトルールの例外：AppenderはINSERT操作のみに適用）。
- IPごとに1回のUPDATEで同一IPの全行を一括更新（重複排除で効率化）。
- バッチサイズ: 1000 IPずつ `prepare()`+ループで処理。

**Refactor:** 大量IP時のパフォーマンスを確認し、必要に応じてトランザクション境界を調整する。

---

### Phase 5: `main.rs` 拡張 — CLIフラグ追加

**目的:** `Ingest` への `--geoip-city`/`--geoip-asn` フラグ追加と `Enrich` サブコマンドを追加する。

**変更:** `ingester/src/main.rs`

**Red:** C-01〜C-05 のCLIテストを記述（失敗する）

**Green — CLIの変更内容:**

```rust
// main.rs

enum Commands {
    Ingest {
        // ...既存フラグ...

        /// Path to GeoLite2-City.mmdb (overrides GEOIP_CITY_PATH env var).
        #[arg(long, value_name = "PATH")]
        geoip_city: Option<PathBuf>,

        /// Path to GeoLite2-ASN.mmdb (overrides GEOIP_ASN_PATH env var).
        #[arg(long, value_name = "PATH")]
        geoip_asn: Option<PathBuf>,
    },

    /// Enrich existing cloudtrail_events rows with GeoIP data.
    Enrich {
        /// Path to the DuckDB database file.
        #[arg(short, long)]
        db: Option<PathBuf>,

        /// Path to GeoLite2-City.mmdb.
        #[arg(long, value_name = "PATH")]
        geoip_city: Option<PathBuf>,

        /// Path to GeoLite2-ASN.mmdb.
        #[arg(long, value_name = "PATH")]
        geoip_asn: Option<PathBuf>,
    },
}
```

**環境変数解決順序:**

1. CLI引数 (`--geoip-city`)
2. 環境変数 (`GEOIP_CITY_PATH`)
3. 省略時: GeoIPなしで動作（エンリッチスキップ）

---

## 4. ファイル変更一覧

| ファイル | 種別 | 変更内容の概要 |
|---------|------|----------------|
| `ingester/src/geoip.rs` | 🆕 新規作成 | `GeoInfo`, `GeoipConfig`, `GeoipEnricher`, `classify_special_ip()` |
| `ingester/src/enrich.rs` | 🆕 新規作成 | `EnrichStats`, `enrich_existing()`, UPDATEバッチ処理 |
| `ingester/src/db.rs` | ✏️ 変更 | `ensure_geo_columns()` 追加、`insert_events_with_geo()` 追加、Appenderを24列対応に変更 |
| `ingester/src/ingest.rs` | ✏️ 変更 | `ingest_core()` に `Option<&GeoipEnricher>` 追加、`ingest_with_geoip()` 公開関数追加 |
| `ingester/src/main.rs` | ✏️ 変更 | `Ingest` にgeoipフラグ追加、`Enrich` サブコマンド追加、env var解決ロジック追加 |
| `ingester/src/lib.rs` | ✏️ 変更 | `pub mod geoip;` と `pub mod enrich;` を追加 |
| `ingester/Cargo.toml` | ✏️ 変更 | `maxminddb` 依存を追加 |
| `ingester/tests/testdata/geoip/GeoLite2-City-Test.mmdb` | 🆕 追加 | テスト用mmdbフィクスチャ |
| `ingester/tests/testdata/geoip/GeoLite2-ASN-Test.mmdb` | 🆕 追加 | テスト用mmdbフィクスチャ |
| `ingester/tests/cli_test.rs` | ✏️ 変更 | C-01〜C-05のCLIテスト追加 |

---

## 5. Cargo.toml 変更

`ingester/Cargo.toml` の `[dependencies]` セクションに追加:

```toml
# MaxMind GeoIP2 / GeoLite2 .mmdb database reader
maxminddb = "0.24"
```

**補足:**

- `std::net::IpAddr` は標準ライブラリのため追加依存なし。
- `maxminddb 0.24` は Rust edition 2021 以降と互換（本プロジェクトは edition 2024）。
- `maxminddb::Reader<Mmap>` は `Send + Sync` を実装しており、rayon 並列イテレータで安全に共有可能。

---

## 6. テスト戦略

### テスト用 `.mmdb` ファイルの調達方法

MaxMind は [MaxMind-DB GitHub リポジトリ](https://github.com/maxmind/MaxMind-DB) でテスト用 `.mmdb` ファイルを公開している。以下をダウンロードして `ingester/tests/testdata/geoip/` に配置する:

| ファイル | 用途 | 取得元 |
|---------|------|--------|
| `GeoLite2-City-Test.mmdb` | cityルックアップテスト | MaxMind-DB repo `test-data/` |
| `GeoLite2-ASN-Test.mmdb` | ASNルックアップテスト | MaxMind-DB repo `test-data/` |

これらはMIT相当のライセンスで提供されており、テストフィクスチャとしてリポジトリにコミット可能。

**既知のテストIP（`GeoLite2-City-Test.mmdb` に含まれる）:**

| IP | 期待値 |
|----|--------|
| `81.2.69.160` | country_code=`"GB"`, city=`"London"` |
| `2.125.160.216` | country_code=`"GB"`, city=`"Boxford"` |
| `216.160.83.56` | country_code=`"US"` |

### モック戦略（3層構成）

GeoIP ルックアップのユニットテストには、mmdb ファイルを**一切必要としない**テストと、**テスト用 mmdb を使うテスト**の2層構成を採用する:

- **Layer 1（純粋ユニットテスト）:** `classify_special_ip()` はmmdb不要。テストG-01〜G-10が対象。
- **Layer 2（フィクスチャテスト）:** `GeoipEnricher::lookup()` はテスト用mmdbを使用。`env!("CARGO_MANIFEST_DIR")` で絶対パスを解決し、CI環境でも再現可能にする。
- **Layer 3（統合テスト）:** `ingest.rs` の統合テストはテスト用mmdbをフィクスチャとして参照する。

### テストヘルパー（`geoip.rs` の `#[cfg(test)]` ブロック内）

```rust
// Returns the path to testdata/geoip/GeoLite2-City-Test.mmdb
fn test_city_db_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/testdata/geoip/GeoLite2-City-Test.mmdb")
}
```

---

## 7. 既存機能への影響

### 後方互換性

| 影響範囲 | 内容 | 対応方針 |
|---------|------|---------|
| `cloudtrail_events` テーブル | 7カラム追加（全てNULLable） | `ALTER TABLE ADD COLUMN IF NOT EXISTS` で非破壊的移行 |
| 既存 `insert_events()` | Appenderの列数が17→24に変化 | `ensure_geo_columns()` を `ensure_table()` 内で呼び出し、常に24列スキーマを維持 |
| 既存テスト（D#11〜D#13相当） | テーブルスキーマ変更の影響を受ける | `insert_events` を `insert_events_with_geo(conn, events, None)` への委譲ラッパーとして残す |
| `ingest_with_filters()` | シグネチャ変更なし（geoip=Noneのままデフォルト動作） | 変更不要 |

### 既存テストへの影響（要修正）

`db.rs` の既存テストが `insert_events()` を直接呼ぶため、`insert_events_with_geo()` への移行が必要。既存の `insert_events` を `insert_events_with_geo(conn, events, None)` へのインライン委譲ラッパーとして残すことで変更を最小化できる。

---

## 8. エラーハンドリング方針

`anyhow::Result` と `.with_context()` を使ったエラー伝播の方針:

| シナリオ | 挙動 | コンテキストメッセージ例（英語）|
|---------|------|-------------------------------|
| mmdbファイルが存在しない | `Err(...)` を返して起動失敗 | `"Failed to open GeoLite2-City database at {path}"` |
| IP文字列がパース不能（CloudTrailの `"AWS"` 等） | `GeoInfo::all_none()` を返してスキップ（ログ警告） | `"Skipping non-IP source_ip_address: {val}"` |
| mmdbにIPが存在しない | `GeoInfo::all_none()` を返す（エラーなし） | — |
| mmdb形式が壊れている | `Err(...)` を返して起動失敗 | `"Corrupt GeoIP database at {path}"` |
| `enrich` コマンドのDB UPDATE失敗 | `Err(...)` を伝播、中断 | `"Failed to update geo columns for IP {ip}"` |
| GeoIPなしで `ingest` 実行 | 正常動作（geoカラムはNULL） | — |

**重要:** CloudTrail の `sourceIPAddress` フィールドには `"AWS"` のような非IPの文字列が含まれる場合がある（`sts.amazonaws.com` 経由のロール引き受けなど）。これらは `IpAddr::parse()` が失敗するため、警告ログを出しつつ全フィールドNULLでスキップする（推奨方針）。

---

## 9. 将来の拡張性

### agent/dashboard 側での活用

GeoIPカラムが追加されると、`agent/builtin_hunts.yaml` に以下のようなビルトインクエリを追加できる:

```yaml
# agent/builtin_hunts.yaml への追加例

- label: "🌍 Top Source Countries"
  category: "GeoIP Analysis"
  description: "Rank source countries by API call volume"
  sql: |
    SELECT
      geo_country_code,
      geo_country_name,
      COUNT(*) AS event_count,
      COUNT(DISTINCT source_ip_address) AS unique_ips
    FROM cloudtrail_events
    WHERE geo_country_code NOT IN ('PRIVATE', 'LOOPBACK', 'AWS-INTERNAL')
      AND geo_country_code IS NOT NULL
    GROUP BY geo_country_code, geo_country_name
    ORDER BY event_count DESC
    LIMIT 20;

- label: "🚨 Unusual Country Access"
  category: "GeoIP Analysis"
  description: "Detect API calls from unexpected countries"
  prompt: |
    Find all source IPs from countries other than the expected baseline,
    grouped by user identity ARN. Show event counts and countries.
```

### Apache Superset ダッシュボードへの統合

- 地図チャート（Deck.GL Scatter Plot）: `geo_latitude`, `geo_longitude` を使った攻撃元可視化
- `dashboard/assets/` の既存 ZIP に新チャートを追加し、`superset-resync` プロファイルで再同期

### v2+ への拡張候補

- GeoLite2-Connection-Type.mmdb による接続タイプエンリッチ（VPN/Tor検出）
- IPレピュテーションDB（AbuseIPDB等）との統合フックを `GeoipEnricher` に追加
- `geo_asn` フィールドを使ったCloud Provider検出（`AS16509` = AWS等）

---

## 10. 設計決定事項（確定）

| # | 項目 | 決定内容 |
|---|------|---------|
| 1 | **`insert_events` の移行方針** | **後方互換性不要** — `insert_events()` を削除し `insert_events_with_geo()` に一括移行する。既存テスト (#11〜#13) も新APIに合わせて修正する。 |
| 2 | **CloudTrail の `"AWS"` 文字列の扱い** | **全フィールドNULL** — `IpAddr::parse()` が失敗する非IP文字列は警告ログを出力し、geo全フィールドをNULLとしてスキップする。 |
| 3 | **テスト用mmdbファイルのコミット方針** | **リポジトリにコミット** — MaxMind-DBリポジトリのテスト用mmdbを `ingester/tests/testdata/geoip/` にコミットする。 |


