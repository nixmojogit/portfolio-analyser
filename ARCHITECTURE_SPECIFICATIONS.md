# Portfolio Analysis System
## Architecture Specification
*Version 1.0 — Approach A (SKILLS.md as Design Contract)*
*Platform: Python-based Local Desktop Solution*

---

## 1. Architectural Overview

The system is designed as a **locally-running, Python-based portfolio intelligence platform** with no dependency on paid cloud services. It runs entirely on the user's machine, using free data sources, a local database, and the Claude AI API for NLP-based sentiment scoring.

The architecture is organised into **five horizontal layers**, each containing discrete **functional modules**, each module owning a defined set of **skills** as specified in SKILLS.md.

```
┌──────────────────────────────────────────────────────────────┐
│                   CONFIGURATION LAYER                        │
│        System · Portfolio · Goals · Skills · Thresholds      │
├──────────────────────────────────────────────────────────────┤
│                      DATA LAYER                              │
│     Price · Fundamentals · Shareholding · News · Macro       │
│                    Cache Manager                             │
├──────────────────────────────────────────────────────────────┤
│                  INTELLIGENCE LAYER                          │
│   Technical · Fundamental · Valuation · Sentiment · Risk     │
│          Portfolio Analytics · Scorecard Aggregation         │
├──────────────────────────────────────────────────────────────┤
│                     ACTION LAYER                             │
│   Recommendation · Discovery · Optimisation · Alerts        │
│                     Orchestrator                             │
├──────────────────────────────────────────────────────────────┤
│                  PRESENTATION LAYER                          │
│         Dashboard · Stock Detail · Reports · Exports         │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem depth for data, finance, AI |
| UI Framework | Streamlit | Runs locally in browser; minimal setup; excellent for data dashboards |
| Local Database | SQLite (via SQLAlchemy) | Zero-config, file-based, no server needed |
| Configuration | YAML (via PyYAML) | Human-readable; easy to edit without code changes |
| Price & Fundamentals | `yfinance` | Best free Python library for NSE/BSE data |
| Web Scraping | `requests` + `BeautifulSoup4` | For Screener.in and BSE/NSE filings |
| RSS / News | `feedparser` | Parses ET, Business Standard, Moneycontrol RSS feeds |
| Data Processing | `pandas`, `numpy` | Core data manipulation and computation |
| Technical Indicators | `pandas-ta` | Comprehensive, pandas-native TA library (RSI, MACD, MA etc.) |
| Statistics / Portfolio | `scipy`, `pyportfolioopt` | Correlation matrices, Sharpe ratio, optimisation |
| AI / NLP Sentiment | `anthropic` Python SDK | Claude AI API for news sentiment scoring |
| Scheduling | `APScheduler` | Background data refresh on configurable cadences |
| PDF Reports | `fpdf2` | Lightweight PDF generation; no external dependencies |
| Excel Exports | `openpyxl` | Excel file generation |
| Logging | Python `logging` (built-in) | Structured local logs |
| Environment | `python-dotenv` | Manage API keys (Claude) via `.env` file |

---

## 3. Project Folder Structure

```
portfolio_analyser/
│
├── config/                         # All configuration files (YAML)
│   ├── system.yaml                 # Global settings, paths, logging level
│   ├── portfolio.yaml              # Holdings, buy prices, thesis notes
│   ├── goals.yaml                  # Active goals, target sector allocations
│   ├── thresholds.yaml             # All metric healthy/caution/red thresholds
│   ├── scorecard_weights.yaml      # Scorecard weights for overall score
│   └── skills.yaml                 # Skill enable/disable toggles + cache TTLs
│
├── data/
│   ├── cache/                      # Local SQLite cache for API responses
│   │   └── market_data.db
│   ├── portfolio/                  # Portfolio state, history, thesis logs
│   │   └── portfolio.db
│   └── exports/                    # PDF reports, Excel, CSV exports
│
├── src/
│   ├── layers/
│   │   ├── configuration/
│   │   │   └── config_manager.py   # Loads and validates all YAML configs
│   │   │
│   │   ├── data/
│   │   │   ├── price_module.py
│   │   │   ├── fundamentals_module.py
│   │   │   ├── shareholding_module.py
│   │   │   ├── news_module.py
│   │   │   ├── macro_module.py
│   │   │   └── cache_manager.py
│   │   │
│   │   ├── intelligence/
│   │   │   ├── technical_module.py
│   │   │   ├── fundamental_scoring_module.py
│   │   │   ├── valuation_scoring_module.py
│   │   │   ├── sentiment_module.py
│   │   │   ├── risk_module.py
│   │   │   ├── portfolio_analytics_module.py
│   │   │   └── scorecard_aggregator.py
│   │   │
│   │   ├── action/
│   │   │   ├── recommendation_engine.py   # G1
│   │   │   ├── discovery_engine.py        # G2
│   │   │   ├── optimisation_engine.py     # G3
│   │   │   ├── alert_manager.py
│   │   │   └── orchestrator.py
│   │   │
│   │   └── presentation/
│   │       ├── dashboard.py
│   │       ├── stock_detail_view.py
│   │       ├── portfolio_view.py
│   │       ├── report_generator.py
│   │       └── export_manager.py
│   │
│   └── utils/
│       ├── logger.py
│       ├── validators.py
│       └── helpers.py
│
├── tests/                          # Unit tests per module
│
├── SKILLS.md                       # Master skill registry and design contract
├── requirements.txt
├── .env                            # Claude API key (not committed to version control)
├── .gitignore
├── app.py                          # Streamlit app entry point
└── README.md
```

---

## 4. Layer-by-Layer Design

---

### 4.1 Configuration Layer

**Purpose:** Single source of truth for all system behaviour. No thresholds, weights, or toggles are hardcoded in logic modules.

#### Modules

**Config Manager**
- Loads all YAML config files at startup
- Validates config completeness and type correctness
- Exposes a unified config object consumed by all other layers
- Reloads config on demand (without restarting the app)

#### Key Configuration Files

**`system.yaml`** — Global settings
```yaml
app_name: "Portfolio Analyser"
log_level: "INFO"
db_path: "data/cache/market_data.db"
portfolio_db_path: "data/portfolio/portfolio.db"
export_path: "data/exports/"
market: "NSE"                        # NSE or BSE
benchmark_index: "^NSEI"             # Nifty 50
risk_free_rate: 0.065                # Current RBI repo rate (configurable)
```

**`portfolio.yaml`** — Holdings definition
```yaml
holdings:
  - ticker: "RELIANCE.NS"
    name: "Reliance Industries"
    sector: "Energy"
    buy_price: 2450.00
    quantity: 10
    buy_date: "2024-01-15"
    stop_loss_pct: 8
    thesis: "Dominant conglomerate with Jio and retail growth engines"
    thesis_intact: true
```

**`goals.yaml`** — Goal configuration
```yaml
active_goals:
  G1: true
  G2: true
  G3: true

target_sector_allocation:           # G3 target weights (%)
  Technology: 25
  Financial Services: 20
  Consumer: 15
  Healthcare: 15
  Energy: 10
  Infrastructure: 10
  Others: 5

rebalancing_drift_threshold: 5      # % drift before rebalancing triggered
max_concentration_per_stock: 15     # % of portfolio max in one stock
min_holdings: 10
max_holdings: 20
```

**`thresholds.yaml`** — All metric thresholds (Green / Amber / Red)
```yaml
revenue_growth_yoy:
  green: 10
  amber: 0
  red: -999

peg_ratio:
  green_max: 1.0
  amber_max: 1.5
  red_above: 1.5

rsi:
  oversold: 30
  overbought: 70
  neutral_low: 40
  neutral_high: 60
# ... all 32 metrics defined here
```

**`scorecard_weights.yaml`** — Scorecard composition
```yaml
overall_score_weights:
  fundamental: 0.30
  valuation: 0.25
  technical: 0.20
  sentiment: 0.15
  risk: 0.10

recommendation_thresholds:
  strong_buy: 75
  hold: 55
  reduce: 35
  exit: 0
```

**`skills.yaml`** — Skill registry and toggles
```yaml
skills:
  SKILL-D01:
    enabled: true
    cache_ttl_hours: 24
  SKILL-I18:
    enabled: true            # Claude AI sentiment — disable to save API calls
    cache_ttl_hours: 12
  SKILL-D05:
    enabled: true            # Screener.in scraping
    cache_ttl_hours: 168     # Weekly refresh (rate limit protection)
```

---

### 4.2 Data Layer

**Purpose:** Acquire, normalise, and cache all raw market data from free sources.

**Core principle:** Every module checks the local SQLite cache before making an external call. Cache TTL is controlled by `skills.yaml`.

#### Modules

| Module | Responsibility | Primary Source | Fallback |
|---|---|---|---|
| Price Module | Historical prices, real-time price, volume, index levels | `yfinance` | NSE unofficial API |
| Fundamentals Module | Revenue, EPS, margins, FCF, ratios | `yfinance` | Screener.in scrape |
| Shareholding Module | Promoter holding, pledge, FII/DII, institutional changes | BSE filings scrape | Screener.in |
| News Module | News headlines, RSS feeds, NSE/BSE announcements | ET/BS/MC RSS + NSE BSE feeds | Google News RSS |
| Macro Module | Repo rate, CPI, GDP, India VIX, GST data | RBI, MOSPI, `yfinance` | World Bank API |
| Cache Manager | Read/write/invalidate local SQLite cache | SQLite (local) | None |

#### Data Flow
```
External Source → Data Module → Cache Manager → SQLite DB → Intelligence Layer
                      ↑               ↓
                  skills.yaml    (TTL check)
                  (enabled?)     (fresh? serve from cache : fetch fresh)
```

---

### 4.3 Intelligence Layer

**Purpose:** Transform raw data into scored, actionable signals. Pure computation — no data fetching, no UI.

#### Modules

| Module | Responsibility | Skills Owned |
|---|---|---|
| Technical Module | MA, RSI, MACD, Beta, momentum, volume signal | SKILL-I01 to I06 |
| Fundamental Scoring Module | Revenue growth, margins, FCF, ROIC, promoter signals | SKILL-I07 to I17 |
| Valuation Scoring Module | PEG, P/E vs sector, EV/EBITDA | Within SKILL-I21 |
| Sentiment Module | Claude AI NLP scoring, insider signal, analyst signal | SKILL-I18 to I20 |
| Risk Module | Stop-loss proximity, concentration, debt, beta risk | SKILL-I31, within SKILL-I24 |
| Portfolio Analytics Module | Correlation matrix, sector allocation, Sharpe ratio, portfolio beta | SKILL-I27 to I30 |
| Scorecard Aggregator | Combine 5 scorecards → Overall Stock Score | SKILL-I21 to I26 |

#### Scoring Architecture
```
Raw Data
   │
   ├─► Technical Module      → Technical Score  (0-100)  ──┐
   ├─► Fundamental Module    → Fundamental Score (0-100) ──┤
   ├─► Valuation Module      → Valuation Score  (0-100)  ──┼─► Scorecard Aggregator
   ├─► Sentiment Module      → Sentiment Score  (0-100)  ──┤    → Overall Stock Score (0-100)
   └─► Risk Module           → Risk Score       (0-100)  ──┘    → Recommendation
```

#### Threshold-to-Score Mapping
Each metric maps its value to a sub-score (0–100) using thresholds from `thresholds.yaml`:
- Green zone → 70–100 points
- Amber zone → 35–69 points
- Red zone → 0–34 points

Sub-scores within a scorecard are averaged (equally weighted by default, configurable).

---

### 4.4 Action Layer

**Purpose:** Translate scores and signals into decisions, recommendations, and alerts.

#### Modules

| Module | Goal | Responsibility |
|---|---|---|
| Recommendation Engine | G1 | Generates Buy/Hold/Reduce/Exit recommendations for existing holdings |
| Discovery Engine | G2 | Screens stock universe, filters candidates, evaluates against scored thresholds |
| Optimisation Engine | G3 | Detects drift, runs correlation checks, generates rebalancing plan |
| Alert Manager | All | Monitors stop-loss, thesis integrity, sector drift — raises alerts |
| Orchestrator | All | Chains skills into goal-specific workflows; manages execution order |

#### Orchestrator — Workflow Design

The orchestrator reads `skills.yaml` to determine which skills are enabled, then executes workflows as ordered skill chains:

**G1 Workflow — Existing Portfolio Recommendation:**
```
Portfolio Config → Fetch Price Data → Fetch Fundamentals → Fetch Shareholding
→ Fetch News → Compute Technical Indicators → Compute Fundamental Scores
→ Compute Valuation Scores → Score Sentiment (Claude AI)
→ Compute Risk Scores → Aggregate Scorecards → Generate Recommendation
→ Check Stop-Loss → Check Thesis Integrity → Raise Alerts → Update Portfolio DB
```

**G2 Workflow — New Stock Discovery:**
```
Goals Config → Load Nifty 500 Universe → Apply Screening Filters
→ Fetch Fundamentals (shortlisted) → Fetch Price Data → Compute All Scores
→ Rank Candidates → Check Correlation vs Existing Portfolio
→ Check Sector Allocation Impact → Generate Ranked Recommendations
```

**G3 Workflow — Portfolio Optimisation:**
```
Portfolio DB → Compute Sector Allocation → Detect Drift
→ Compute Correlation Matrix → Compute Portfolio Beta → Compute Sharpe Ratio
→ Identify Overweight / Underweight Sectors → Match G2 Candidates to Gaps
→ Generate Rebalancing Plan → Raise Rebalancing Alerts
```

#### Scheduling (APScheduler)

| Cadence | Workflow Triggered |
|---|---|
| Daily (market close) | G1 price refresh, stop-loss check, news sentiment |
| Weekly | G1 full technical refresh, G2 discovery scan |
| Monthly | Full fundamentals refresh, shareholding update |
| Quarterly | G3 full portfolio optimisation run |
| Event-driven | NSE/BSE announcement feed triggers immediate re-score |

---

### 4.5 Presentation Layer

**Purpose:** Render all outputs to the user via a local Streamlit dashboard and exportable reports.

#### Modules & Views

| Module | View | Description |
|---|---|---|
| Dashboard | Portfolio Overview | Total value, overall portfolio health, top alerts, goal status |
| Stock Detail View | Per-Stock Drilldown | All 32 metrics, 5 scorecards, overall score, recommendation, price chart |
| Portfolio View | Portfolio Analytics | Sector allocation chart, correlation heatmap, portfolio beta, Sharpe |
| Discovery View | G2 Candidates | Ranked new stock recommendations with scores and rationale |
| Optimisation View | G3 Rebalancing Plan | Current vs target allocation, specific buy/trim/exit actions |
| Alert Panel | Alerts & Triggers | All active stop-loss, thesis, drift and sentiment alerts |
| Report Generator | PDF Summary Report | Full portfolio report exportable as PDF |
| Export Manager | Data Exports | CSV / Excel exports of scores, recommendations, history |

---

## 5. Database Design (SQLite)

### `market_data.db` — Cache Database

| Table | Contents | TTL Managed By |
|---|---|---|
| `price_cache` | OHLCV data per ticker per date | skills.yaml SKILL-D01 |
| `fundamentals_cache` | Financial statement data per ticker | skills.yaml SKILL-D03/D05 |
| `ratios_cache` | Computed ratios per ticker | skills.yaml SKILL-D04 |
| `shareholding_cache` | Promoter, FII/DII data per ticker per quarter | skills.yaml SKILL-D07 |
| `news_cache` | Headlines per ticker with timestamp | skills.yaml SKILL-D09 |
| `sentiment_cache` | Claude AI scored sentiment per ticker | skills.yaml SKILL-I18 |
| `macro_cache` | Repo rate, CPI, GDP, VIX snapshots | skills.yaml SKILL-D11 |

### `portfolio.db` — Portfolio State Database

| Table | Contents |
|---|---|
| `holdings` | Current portfolio — ticker, qty, weighted avg buy price, sector |
| `thesis_log` | Thesis notes and integrity flag history per stock |
| `scores_history` | Daily scorecard and overall score per ticker |
| `recommendations_history` | All generated recommendations with timestamp |
| `alerts_log` | All raised alerts and resolution status |
| `performance_history` | Daily portfolio value, benchmark value, returns |
| `rebalancing_log` | All G3 rebalancing plans and execution status |

---

## 6. SKILLS.md — Structure & Conventions

SKILLS.md is the **canonical design contract** for this system. Every discrete capability is defined as a skill entry. No code should implement a capability that is not first defined in SKILLS.md.

### Skill Entry Format

```markdown
## SKILL-XNN: Skill Name

| Property            | Value                              |
|---------------------|------------------------------------|
| Skill ID            | SKILL-XNN                          |
| Layer               | Data / Intelligence / Action / Presentation |
| Module              | Module name                        |
| Goal Applicability  | G1 / G2 / G3 / All                |
| Status              | Active / Planned / Disabled        |
| Cache TTL           | N hours (if data skill)            |
| AI Dependency       | Yes / No                           |
| External Dependency | Source name / None                 |

### Description
What this skill does in plain language.

### Inputs
- Input 1: type, source
- Input 2: type, source

### Outputs
- Output 1: type, description

### Skill Dependencies
- SKILL-XNN (must run before this skill)

### Implementation Notes
Any constraints, known issues, fallback behaviour, or rate limit considerations.
```

---

## 7. Full Skill Inventory

### Data Layer Skills (D-Series)

| Skill ID | Skill Name | Source | Goal | Status |
|---|---|---|---|---|
| SKILL-D01 | Fetch Historical Price Data | yfinance | All | Active |
| SKILL-D02 | Fetch Real-Time Price Snapshot | yfinance | All | Active |
| SKILL-D03 | Fetch Financial Statements | yfinance | All | Active |
| SKILL-D04 | Fetch Key Ratios & Multiples | yfinance | All | Active |
| SKILL-D05 | Scrape Screener.in Fundamentals | Screener.in | All | Active |
| SKILL-D06 | Fetch NSE Bulk & Block Deals | NSE India | G1, G2 | Active |
| SKILL-D07 | Fetch BSE Shareholding Pattern | BSE India | All | Active |
| SKILL-D08 | Fetch Promoter Pledge Data | BSE / Screener.in | All | Active |
| SKILL-D09 | Fetch RSS News Feeds | ET / BS / MC RSS | All | Active |
| SKILL-D10 | Fetch NSE/BSE Announcements | NSE / BSE feeds | All | Active |
| SKILL-D11 | Fetch Macro Indicators | RBI / MOSPI / yfinance | G1, G3 | Active |
| SKILL-D12 | Fetch Index & Sector Index Data | yfinance / NSE | All | Active |
| SKILL-D13 | Cache Read / Write Manager | SQLite local DB | All | Active |

### Intelligence Layer Skills (I-Series)

| Skill ID | Skill Name | Scorecard | Goal | Status |
|---|---|---|---|---|
| SKILL-I01 | Compute Moving Averages (50D / 200D) | Technical | All | Active |
| SKILL-I02 | Compute RSI (14-day) | Technical | All | Active |
| SKILL-I03 | Compute MACD & Signal | Technical | All | Active |
| SKILL-I04 | Compute Beta | Technical / Risk | All | Active |
| SKILL-I05 | Compute 52-Week Momentum Score | Technical | G1, G2 | Active |
| SKILL-I06 | Compute Volume Signal | Technical | G1, G2 | Active |
| SKILL-I07 | Compute Revenue Growth (YoY / QoQ) | Fundamental | All | Active |
| SKILL-I08 | Compute Margin Trends | Fundamental | All | Active |
| SKILL-I09 | Compute Free Cash Flow & Growth | Fundamental | All | Active |
| SKILL-I10 | Compute PEG Ratio | Valuation | All | Active |
| SKILL-I11 | Compute P/E vs Sector Median | Valuation | All | Active |
| SKILL-I12 | Compute EV/EBITDA | Valuation | All | Active |
| SKILL-I13 | Compute ROIC | Fundamental | All | Active |
| SKILL-I14 | Compute Relative Strength vs Sector | Fundamental | G2, G3 | Active |
| SKILL-I15 | Compute Earnings Surprise % | Sentiment | All | Active |
| SKILL-I16 | Compute Earnings Estimate Revisions | Fundamental | G2 | Active |
| SKILL-I17 | Compute Promoter Holding Signal | Fundamental | All | Active |
| SKILL-I18 | Score News Sentiment via Claude AI | Sentiment | All | Active |
| SKILL-I19 | Compute Insider Activity Signal | Sentiment | G1, G2 | Active |
| SKILL-I20 | Compute Institutional Ownership Change | Sentiment | All | Active |
| SKILL-I21 | Compute Fundamental Scorecard Score | Aggregation | All | Active |
| SKILL-I22 | Compute Technical Scorecard Score | Aggregation | All | Active |
| SKILL-I23 | Compute Valuation Scorecard Score | Aggregation | All | Active |
| SKILL-I24 | Compute Risk Scorecard Score | Aggregation | All | Active |
| SKILL-I25 | Compute Sentiment Scorecard Score | Aggregation | All | Active |
| SKILL-I26 | Compute Overall Stock Score | Aggregation | All | Active |
| SKILL-I27 | Compute Inter-Stock Correlation Matrix | Portfolio | G3 | Active |
| SKILL-I28 | Compute Sector Allocation | Portfolio | G3 | Active |
| SKILL-I29 | Compute Portfolio Beta | Portfolio | G3 | Active |
| SKILL-I30 | Compute Portfolio Sharpe Ratio | Portfolio | G3 | Active |
| SKILL-I31 | Compute Stop-Loss Proximity | Risk | G1, G3 | Active |

### Action Layer Skills (A-Series)

| Skill ID | Skill Name | Goal | Status |
|---|---|---|---|
| SKILL-A01 | Generate Stock Recommendation | G1 | Active |
| SKILL-A02 | Screen Stock Universe (Nifty 500) | G2 | Active |
| SKILL-A03 | Evaluate New Stock Candidate | G2 | Active |
| SKILL-A04 | Rank Discovery Candidates | G2 | Active |
| SKILL-A05 | Detect Sector Allocation Drift | G3 | Active |
| SKILL-A06 | Generate Portfolio Rebalancing Plan | G3 | Active |
| SKILL-A07 | Detect Stop-Loss Breach | G1, G3 | Active |
| SKILL-A08 | Detect Thesis Integrity Change | G1, G3 | Active |
| SKILL-A09 | Generate Alert | All | Active |
| SKILL-A10 | Orchestrate G1 Workflow | G1 | Active |
| SKILL-A11 | Orchestrate G2 Workflow | G2 | Active |
| SKILL-A12 | Orchestrate G3 Workflow | G3 | Active |
| SKILL-A13 | Schedule Automated Refresh | All | Active |

### Presentation Layer Skills (P-Series)

| Skill ID | Skill Name | Goal | Status |
|---|---|---|---|
| SKILL-P01 | Render Portfolio Overview Dashboard | All | Active |
| SKILL-P02 | Render Stock Detail & Scorecard View | G1 | Active |
| SKILL-P03 | Render Discovery Candidates View | G2 | Active |
| SKILL-P04 | Render Portfolio Optimisation View | G3 | Active |
| SKILL-P05 | Render Alerts Panel | All | Active |
| SKILL-P06 | Generate PDF Portfolio Report | All | Active |
| SKILL-P07 | Export Scores & Recommendations to Excel | All | Active |
| SKILL-P08 | Export Raw Data to CSV | All | Active |

**Total: 13 Data Skills + 31 Intelligence Skills + 13 Action Skills + 8 Presentation Skills = 65 Skills**

---

## 8. Key Design Principles

| Principle | Implementation |
|---|---|
| **Skills are atomic** | Each skill does exactly one thing — no skill fetches data AND computes a metric |
| **Skills are stateless** | Inputs in, outputs out — no skill retains state between runs |
| **Skills are composable** | Orchestrator chains skills into workflows; skills have no knowledge of each other |
| **Skills declare dependencies** | Each SKILLS.md entry lists prerequisite skills — orchestrator respects execution order |
| **Configuration drives behaviour** | All thresholds, weights, toggles are in YAML — no magic numbers in code |
| **Cache before fetch** | Every data skill checks cache first; external calls only on cache miss or TTL expiry |
| **Fail gracefully** | If a data source fails, skill logs the failure, uses cached data if available, and flags the metric as stale rather than crashing |
| **Approach A discipline** | Every new capability is defined in SKILLS.md before code is written |

---

## 9. Configurable Behaviours Summary

Everything in this table is changeable via config files — no code changes needed:

| Behaviour | Config File | Key |
|---|---|---|
| Add / remove a holding | portfolio.yaml | holdings list |
| Change stop-loss % per stock | portfolio.yaml | stop_loss_pct |
| Change scorecard weights | scorecard_weights.yaml | overall_score_weights |
| Change metric thresholds | thresholds.yaml | per-metric keys |
| Enable / disable a skill | skills.yaml | enabled: true/false |
| Change cache refresh frequency | skills.yaml | cache_ttl_hours |
| Change target sector allocation | goals.yaml | target_sector_allocation |
| Change rebalancing drift threshold | goals.yaml | rebalancing_drift_threshold |
| Change benchmark index | system.yaml | benchmark_index |
| Change risk-free rate | system.yaml | risk_free_rate |
| Activate / deactivate a goal | goals.yaml | active_goals |

---

## 10. SKILLS.md Governance Rules

1. **No skill is coded before it is defined in SKILLS.md**
2. **No skill is modified without updating its SKILLS.md entry first**
3. **Skill IDs are never reused** — deprecated skills are marked `Status: Deprecated`, not deleted
4. **Dependencies must be acyclic** — circular skill dependencies are not permitted
5. **Each skill has exactly one owning module** — shared logic goes into `utils/`
6. **SKILLS.md is version-controlled** — every change is committed with a description

---

## 11. Constraints & Known Limitations

| Constraint | Impact | Mitigation |
|---|---|---|
| NSE unofficial API can break on site changes | Price/F&O data disruption | yfinance as primary fallback |
| Screener.in scraping rate limits | Fundamentals refresh may be slow | Weekly TTL; scrape one stock at a time with delay |
| yfinance data gaps for small/mid caps | Some metrics unavailable | Flag as N/A in scorecard; don't penalise score |
| Claude AI API has per-call cost | Sentiment scoring has marginal cost | Cache sentiment scores (12h TTL); only score on new headlines |
| No real-time streaming data | Prices delayed by yfinance | Acceptable for investment decisions (not trading) |
| Single user, local machine | No multi-device sync | SQLite file can be backed up manually |
| Free news APIs limited to 100 calls/day | Limited news coverage | Prioritise portfolio stocks; RSS feeds are unlimited |

---

*Document Status: Architecture Specified — Ready for SKILLS.md authoring and phased build planning*
*Next Step: Author full SKILLS.md with detailed skill definitions, then plan build phases*