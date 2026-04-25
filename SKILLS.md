# SKILLS.md — Portfolio Analysis System
## Master Skill Registry & Design Contract
*Version 1.0*
*Total Skills: 66 (14 Data · 31 Intelligence · 13 Action · 8 Presentation)*

---

## Governance Rules

1. No skill is coded before it is defined in this document
2. No skill is modified without updating its entry here first
3. Skill IDs are never reused — deprecated skills are marked `Status: Deprecated`
4. Skill dependencies must be acyclic — no circular dependencies permitted
5. Each skill has exactly one owning module — shared logic goes into `src/utils/`
6. This document is version-controlled — every change is committed with a description

---

## Skill Entry Format

Each skill entry follows this structure:

| Property | Value |
|---|---|
| Skill ID | SKILL-XNN |
| Layer | Data / Intelligence / Action / Presentation |
| Module | Owning module filename |
| Goal Applicability | G1 / G2 / G3 / All |
| Status | Active / Planned / Disabled / Deprecated |
| Cache TTL | N hours (data skills only) |
| AI Dependency | Yes / No |
| External Dependency | Source name / None |

---

---

# DATA LAYER SKILLS (D-Series)

---

## SKILL-D01: Fetch Historical Price Data

| Property | Value |
|---|---|
| Skill ID | SKILL-D01 |
| Layer | Data |
| Module | price_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 24 hours |
| AI Dependency | No |
| External Dependency | Yahoo Finance (yfinance) |

### Description
Fetches historical OHLCV (Open, High, Low, Close, Volume) price data for a given stock ticker from Yahoo Finance. Uses NSE ticker format (e.g. `RELIANCE.NS`). Checks cache before making external call. Stores result in `price_cache` table in `market_data.db`.

### Inputs
- `ticker`: string — NSE/BSE ticker symbol (e.g. `RELIANCE.NS`)
- `period`: string — lookback period (default: `2y` for 2 years)
- `interval`: string — data frequency (default: `1d` for daily)

### Outputs
- `price_df`: pandas DataFrame — columns: Date, Open, High, Low, Close, Volume
- `cache_timestamp`: datetime — when data was last fetched

### Skill Dependencies
- SKILL-D13 (cache check before fetch)

### Implementation Notes
- Always use `.NS` suffix for NSE stocks and `.BO` for BSE stocks
- Minimum 1 year of data required for 200-day MA computation
- On fetch failure, return most recent cached data and log a stale data warning
- Rate limit: yfinance allows ~2000 calls/hour; no throttling needed for typical portfolio sizes

---

## SKILL-D02: Fetch Real-Time Price Snapshot

| Property | Value |
|---|---|
| Skill ID | SKILL-D02 |
| Layer | Data |
| Module | price_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 1 hour |
| AI Dependency | No |
| External Dependency | Yahoo Finance (yfinance) |

### Description
Fetches the current market price, day change %, 52-week high, 52-week low, and average volume for a given ticker. Used for real-time portfolio valuation and stop-loss monitoring.

### Inputs
- `ticker`: string — NSE/BSE ticker symbol
- `tickers_list`: list — optionally fetch multiple tickers in one call

### Outputs
- `current_price`: float
- `day_change_pct`: float
- `week_52_high`: float
- `week_52_low`: float
- `avg_volume`: float
- `market_cap`: float

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Use `yfinance.Ticker(ticker).fast_info` for lightweight real-time snapshot
- If market is closed, returns last closing price
- Batch multiple tickers using `yfinance.download()` for efficiency

---

## SKILL-D03: Fetch Financial Statements

| Property | Value |
|---|---|
| Skill ID | SKILL-D03 |
| Layer | Data |
| Module | fundamentals_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 168 hours (weekly) |
| AI Dependency | No |
| External Dependency | Yahoo Finance (yfinance) |

### Description
Fetches income statement, balance sheet, and cash flow statement for a given ticker using yfinance. Retrieves both annual and quarterly data. Stores in `fundamentals_cache` table.

### Inputs
- `ticker`: string — NSE/BSE ticker symbol
- `frequency`: string — `annual` or `quarterly` (default: both)

### Outputs
- `income_statement`: pandas DataFrame — Revenue, Gross Profit, Operating Income, Net Income, EPS
- `balance_sheet`: pandas DataFrame — Total Assets, Total Debt, Equity, Current Assets, Current Liabilities
- `cash_flow`: pandas DataFrame — Operating CF, CapEx, Free Cash Flow

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Use `yfinance.Ticker(ticker).financials` for annual income statement
- Use `yfinance.Ticker(ticker).quarterly_financials` for quarterly
- Some Indian mid/small caps may have incomplete data — flag missing fields as `NaN`
- Do not crash on missing data — log warning and continue with available fields

---

## SKILL-D04: Fetch Key Ratios & Multiples

| Property | Value |
|---|---|
| Skill ID | SKILL-D04 |
| Layer | Data |
| Module | fundamentals_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 24 hours |
| AI Dependency | No |
| External Dependency | Yahoo Finance (yfinance) |

### Description
Fetches pre-computed valuation ratios and key metrics from Yahoo Finance including P/E, P/B, P/S, EV/EBITDA, dividend yield, beta, and analyst targets.

### Inputs
- `ticker`: string — NSE/BSE ticker symbol

### Outputs
- `pe_ratio`: float
- `forward_pe`: float
- `pb_ratio`: float
- `ps_ratio`: float
- `ev_ebitda`: float
- `beta`: float
- `dividend_yield`: float
- `analyst_target_price`: float
- `analyst_recommendation`: string

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Use `yfinance.Ticker(ticker).info` dictionary
- Some ratios may be absent for Indian stocks — handle `KeyError` gracefully
- `beta` from yfinance uses S&P 500 as benchmark; note this in output metadata for Indian stocks

---

## SKILL-D05: Scrape Screener.in Fundamentals

| Property | Value |
|---|---|
| Skill ID | SKILL-D05 |
| Layer | Data |
| Module | fundamentals_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 168 hours (weekly) |
| AI Dependency | No |
| External Dependency | Screener.in (web scraping) |

### Description
Scrapes Screener.in stock pages to supplement yfinance data with deeper fundamental history including ROIC, EV/EBITDA, 10-year financial trends, and peer comparison data not available via yfinance.

### Inputs
- `ticker`: string — Screener.in company name or BSE code (e.g. `RELIANCE`)

### Outputs
- `roic`: float — Return on Invested Capital
- `roce`: float — Return on Capital Employed
- `ev_ebitda_screener`: float
- `promoter_holding_pct`: float
- `roe_history`: list of floats — last 5 years
- `revenue_history`: list of floats — last 5 years
- `net_profit_history`: list of floats — last 5 years
- `peer_comparison`: pandas DataFrame — sector peers with key ratios

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Use `requests` + `BeautifulSoup4` for scraping
- Add 2-3 second delay between requests to avoid rate limiting
- Screener.in URL format: `https://www.screener.in/company/TICKER/`
- Cache aggressively (weekly TTL) to minimise scraping frequency
- If scrape fails, return `None` for affected fields and log warning — do not crash

---

## SKILL-D06: Fetch NSE Bulk & Block Deals

| Property | Value |
|---|---|
| Skill ID | SKILL-D06 |
| Layer | Data |
| Module | shareholding_module.py |
| Goal Applicability | G1, G2 |
| Status | Active |
| Cache TTL | 24 hours |
| AI Dependency | No |
| External Dependency | NSE India (unofficial API) |

### Description
Fetches bulk deal and block deal data from NSE India for a given ticker and date range. Large bulk/block deals by institutional investors are a proxy for smart money activity in the Indian market.

### Inputs
- `ticker`: string — NSE ticker (without `.NS` suffix)
- `days_lookback`: int — number of days to look back (default: 30)

### Outputs
- `bulk_deals`: pandas DataFrame — Date, Client, Buy/Sell, Quantity, Price
- `block_deals`: pandas DataFrame — Date, Client, Buy/Sell, Quantity, Price
- `net_institutional_direction`: string — `buying`, `selling`, or `neutral`

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- NSE bulk deal endpoint: `https://www.nseindia.com/api/block-deal`
- Requires session headers to mimic browser request — use `requests.Session()` with appropriate headers
- NSE API can change without notice — wrap in try/except and return empty DataFrame on failure
- Flag data as unavailable rather than crashing if NSE endpoint is unreachable

---

## SKILL-D07: Fetch BSE Shareholding Pattern

| Property | Value |
|---|---|
| Skill ID | SKILL-D07 |
| Layer | Data |
| Module | shareholding_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 720 hours (monthly) |
| AI Dependency | No |
| External Dependency | BSE India / Screener.in |

### Description
Fetches quarterly shareholding pattern data including promoter holding %, FII holding %, DII holding %, and public holding % from BSE filings or Screener.in. Compares current quarter to previous quarter to identify direction of change.

### Inputs
- `ticker`: string — BSE scrip code or company name
- `quarters`: int — number of quarters to fetch (default: 4)

### Outputs
- `promoter_holding_pct`: float — current quarter
- `fii_holding_pct`: float — current quarter
- `dii_holding_pct`: float — current quarter
- `public_holding_pct`: float — current quarter
- `promoter_change_qoq`: float — change from previous quarter
- `fii_change_qoq`: float — change from previous quarter
- `dii_change_qoq`: float — change from previous quarter
- `shareholding_history`: pandas DataFrame — last N quarters

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Primary source: Screener.in shareholding section (most reliable free source)
- Quarterly data — refresh monthly TTL is sufficient
- Flag significant changes (> 2% in a quarter) for alert generation

---

## SKILL-D08: Fetch Promoter Pledge Data

| Property | Value |
|---|---|
| Skill ID | SKILL-D08 |
| Layer | Data |
| Module | shareholding_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 720 hours (monthly) |
| AI Dependency | No |
| External Dependency | BSE India / Screener.in |

### Description
Fetches promoter pledge percentage data — the proportion of promoter-held shares that are pledged as collateral. High pledge % is a critical risk indicator unique to Indian markets.

### Inputs
- `ticker`: string — BSE scrip code or company name

### Outputs
- `pledge_pct`: float — % of promoter shares pledged
- `pledge_change_qoq`: float — change from previous quarter
- `pledge_trend`: string — `increasing`, `decreasing`, or `stable`

### Skill Dependencies
- SKILL-D13 (cache check)
- SKILL-D07 (promoter holding context)

### Implementation Notes
- Pledge data available on Screener.in and BSE filings
- Threshold: > 30% pledge is a serious red flag — trigger alert via SKILL-A09
- Increasing pledge trend over 2+ quarters = escalating risk signal

---

## SKILL-D09: Fetch RSS News Feeds

| Property | Value |
|---|---|
| Skill ID | SKILL-D09 |
| Layer | Data |
| Module | news_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 6 hours |
| AI Dependency | No |
| External Dependency | ET / Business Standard / Moneycontrol RSS |

### Description
Fetches financial news headlines and summaries from RSS feeds of major Indian financial publications. Filters results by company name or ticker to return stock-specific news. Used as input for sentiment scoring.

### Inputs
- `company_name`: string — company name to filter headlines (e.g. `Reliance`)
- `ticker`: string — ticker for additional filtering
- `days_lookback`: int — number of days of news to fetch (default: 30)

### Outputs
- `headlines`: list of dicts — each containing: title, summary, source, published_date, url

### RSS Feed Sources
- Economic Times Markets: `https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms`
- Business Standard Markets: `https://www.business-standard.com/rss/markets-106.rss`
- Moneycontrol Markets: `https://www.moneycontrol.com/rss/marketsnews.xml`
- Google News (filtered): `https://news.google.com/rss/search?q={company_name}+stock+NSE`

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Use `feedparser` library for RSS parsing
- Filter headlines by company name match (case-insensitive)
- Deduplicate headlines across sources by title similarity
- RSS feeds are unlimited — no rate limit concerns
- Store raw headlines in `news_cache` table before sentiment scoring

---

## SKILL-D10: Fetch NSE/BSE Corporate Announcements

| Property | Value |
|---|---|
| Skill ID | SKILL-D10 |
| Layer | Data |
| Module | news_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 6 hours |
| AI Dependency | No |
| External Dependency | NSE India / BSE India |

### Description
Fetches official corporate announcements from NSE/BSE for a given ticker — including earnings releases, board meeting notices, dividend announcements, insider trading disclosures, and regulatory filings.

### Inputs
- `ticker`: string — NSE ticker (without `.NS`)
- `days_lookback`: int — days to look back (default: 30)

### Outputs
- `announcements`: list of dicts — each containing: date, subject, category, exchange, url
- `earnings_announcements`: list — filtered earnings-related announcements
- `insider_disclosures`: list — filtered insider trading disclosures

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- NSE announcements endpoint: `https://www.nseindia.com/api/corp-info`
- BSE announcements: `https://www.bseindia.com/corporates/ann.html`
- Prioritise official announcements over news RSS for earnings and insider data
- Event-driven trigger: new announcement should trigger immediate re-score of affected stock

---

## SKILL-D11: Fetch Macro Indicators

| Property | Value |
|---|---|
| Skill ID | SKILL-D11 |
| Layer | Data |
| Module | macro_module.py |
| Goal Applicability | G1, G3 |
| Status | Active |
| Cache TTL | 168 hours (weekly) |
| AI Dependency | No |
| External Dependency | RBI / MOSPI / yfinance |

### Description
Fetches key Indian macroeconomic indicators used as contextual inputs for portfolio-level decisions and sector sensitivity assessments.

### Inputs
- None (fetches all macro indicators in one call)

### Outputs
- `repo_rate`: float — RBI repo rate (%)
- `cpi_inflation`: float — latest CPI (%)
- `gdp_growth`: float — latest GDP growth rate (%)
- `india_vix`: float — India VIX from NSE
- `usd_inr`: float — USD/INR exchange rate
- `nifty_pe`: float — Nifty 50 index P/E ratio

### Data Sources
- Repo rate: RBI website scrape
- India VIX: `yfinance` (`^INDIAVIX`)
- USD/INR: `yfinance` (`USDINR=X`)
- GDP/CPI: World Bank open API (`api.worldbank.org`)

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Macro data changes slowly — weekly TTL is sufficient
- World Bank API is free and requires no API key
- Use macro indicators as contextual modifiers in portfolio-level scoring, not individual stock scoring

---

## SKILL-D12: Fetch Index & Sector Index Data

| Property | Value |
|---|---|
| Skill ID | SKILL-D12 |
| Layer | Data |
| Module | price_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 24 hours |
| AI Dependency | No |
| External Dependency | Yahoo Finance (yfinance) |

### Description
Fetches historical and current price data for benchmark indices (Nifty 50, Sensex) and Nifty sector indices (Nifty Bank, IT, Pharma, FMCG, Auto, Energy etc.). Used for relative strength computation and sector trend analysis.

### Inputs
- `indices`: list — list of index tickers (e.g. `['^NSEI', '^BSESN', '^CNXIT']`)
- `period`: string — lookback period (default: `1y`)

### Outputs
- `index_data`: dict of pandas DataFrames — keyed by index ticker
- `sector_returns`: dict — 1M, 3M, 6M, 1Y returns per sector index

### Nifty Sector Index Tickers (yfinance)
- Nifty 50: `^NSEI`
- Sensex: `^BSESN`
- Nifty Bank: `^NSEBANK`
- Nifty IT: `^CNXIT`
- Nifty Pharma: `^CNXPHARMA`
- Nifty FMCG: `^CNXFMCG`
- Nifty Auto: `^CNXAUTO`
- Nifty Energy: `^CNXENERGY`

### Skill Dependencies
- SKILL-D13 (cache check)

### Implementation Notes
- Index data is the baseline for computing Beta and Relative Strength
- Always fetch Nifty 50 as the primary benchmark for all relative computations

---

## SKILL-D13: Cache Read / Write Manager

| Property | Value |
|---|---|
| Skill ID | SKILL-D13 |
| Layer | Data |
| Module | cache_manager.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (manages TTL for all other skills) |
| AI Dependency | No |
| External Dependency | None (SQLite local) |

### Description
Central cache management skill. All data skills call this before making external API requests. Reads from and writes to `market_data.db` (SQLite). Checks TTL per skill as defined in `skills.yaml`. Returns cached data if fresh; signals fetch required if stale or absent.

### Inputs
- `skill_id`: string — the calling skill's ID (used to look up TTL from skills.yaml)
- `cache_key`: string — unique identifier for the cached record (e.g. `RELIANCE.NS_price_1d`)
- `data`: any (optional) — data to write to cache

### Outputs
- `cache_hit`: bool — True if fresh cache exists
- `cached_data`: any — the cached data if cache_hit is True
- `cache_age_hours`: float — age of cached data in hours

### Skill Dependencies
- None (foundational skill — no dependencies)

### Implementation Notes
- Uses SQLite `sqlite3` built-in module — no additional library needed
- Cache key format: `{ticker}_{data_type}_{parameters}`
- TTL is read from `skills.yaml` at runtime — configurable without code changes
- On write: store data as JSON string with timestamp in SQLite
- On read: compare current time to stored timestamp against TTL
- All cache operations wrapped in try/except — cache failure must never crash the application

---

## SKILL-D14: Import Portfolio from Excel

| Property | Value |
|---|---|
| Skill ID | SKILL-D14 |
| Layer | Data |
| Module | fundamentals_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (one-time import) |
| AI Dependency | No |
| External Dependency | None (local file) |

### Description
Reads the user's current portfolio holdings from a `.xlsx` file in `data/input/`, validates each row, and writes to the `holdings` table in `portfolio.db`. Quantity represents the **current verified holding quantity** — not derived from transactions. Buy Price is the **weighted average cost** already known by the user. This is a one-time import skill run at initial setup.

### Inputs
- `file_path`: string — path to `.xlsx` file (default: `data/input/portfolio.xlsx`)

### Expected Excel Columns (Single Worksheet, One Holding Per Row)
- `Ticker` (required): NSE ticker symbol — skill auto-appends `.NS` if suffix missing
- `Company Name` (required): Full company name
- `Sector` (required): Sector classification
- `Buy Price` (required): Weighted average purchase price per share in INR
- `Quantity` (required): Current verified holding quantity

### Outputs
- `holdings_df`: pandas DataFrame — validated and normalised holdings
- `import_status`: string — `success`, `partial` (with warnings), or `failed`
- `validation_errors`: list — any rows with missing or invalid data

### Skill Dependencies
- SKILL-D13 (writes to portfolio.db after import)

### Implementation Notes
- Use `openpyxl` for Excel reading (already in requirements.txt)
- Validate all required columns exist before processing
- Auto-append `.NS` to tickers that don't have exchange suffix
- Reject rows with missing required fields — log as validation errors
- Buy Date is not collected — `buy_date` column in portfolio.db is always NULL
- Stop Loss % defaults to 8% — configurable per holding after import
- Do not overwrite existing holdings without explicit user confirmation
- After successful import write holdings to `portfolio.db`

---
---

# INTELLIGENCE LAYER SKILLS (I-Series)

---

## SKILL-I01: Compute Moving Averages

| Property | Value |
|---|---|
| Skill ID | SKILL-I01 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes Simple Moving Averages (SMA) for 50-day and 200-day periods using historical price data. Determines price position relative to each MA and identifies Golden Cross / Death Cross events.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01 (Close prices required)

### Outputs
- `sma_50`: float — current 50-day SMA value
- `sma_200`: float — current 200-day SMA value
- `price_vs_sma50_pct`: float — % above/below 50D MA
- `price_vs_sma200_pct`: float — % above/below 200D MA
- `trend_signal`: string — `bullish`, `neutral`, or `bearish`
- `golden_cross`: bool — 50D MA recently crossed above 200D MA
- `death_cross`: bool — 50D MA recently crossed below 200D MA

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Implemented using `pandas.DataFrame.rolling().mean()`
- Minimum 200 trading days of data required
- Golden/Death cross detected within last 10 trading days

---

## SKILL-I02: Compute RSI

| Property | Value |
|---|---|
| Skill ID | SKILL-I02 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the 14-day Relative Strength Index (RSI) using the Wilder smoothing method. Determines overbought/oversold condition and momentum direction.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01 (Close prices required)
- `period`: int — RSI period (default: 14)

### Outputs
- `rsi_value`: float — current RSI value (0–100)
- `rsi_signal`: string — `oversold` (<30), `neutral` (30–70), `overbought` (>70)
- `rsi_trend`: string — `rising` or `falling` (based on last 5 days)

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Implemented using standard Wilder RSI formula in pandas/numpy
- RSI < 30 with strong fundamentals = potential buy signal
- RSI > 70 with weak sentiment = potential exit signal

---

## SKILL-I03: Compute MACD & Signal

| Property | Value |
|---|---|
| Skill ID | SKILL-I03 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes MACD line (12-day EMA minus 26-day EMA), Signal line (9-day EMA of MACD), and Histogram. Identifies bullish and bearish crossovers.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01

### Outputs
- `macd_line`: float — current MACD value
- `signal_line`: float — current Signal line value
- `histogram`: float — MACD minus Signal
- `macd_signal`: string — `bullish_crossover`, `bearish_crossover`, or `neutral`
- `crossover_date`: date — date of most recent crossover (if within 10 days)

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Implemented using `pandas.DataFrame.ewm(span=N)` for EMA computation
- Crossover detected when MACD crosses Signal line within last 5 trading days

---

## SKILL-I04: Compute Beta

| Property | Value |
|---|---|
| Skill ID | SKILL-I04 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes Beta of a stock relative to the Nifty 50 index using 1-year daily returns. Beta measures the stock's sensitivity to market movements.

### Inputs
- `price_df`: pandas DataFrame — stock price history from SKILL-D01
- `index_df`: pandas DataFrame — Nifty 50 price history from SKILL-D12

### Outputs
- `beta`: float — computed Beta value
- `beta_signal`: string — `low` (<0.8), `moderate` (0.8–1.2), `high` (>1.2)

### Skill Dependencies
- SKILL-D01
- SKILL-D12

### Implementation Notes
- Computed as `Covariance(stock_returns, index_returns) / Variance(index_returns)`
- Uses 252 trading days (1 year) as rolling window
- Implemented using `numpy.cov()` and `numpy.var()`

---

## SKILL-I05: Compute 52-Week Momentum Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I05 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | G1, G2 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes a momentum score based on the stock's current price position relative to its 52-week high and low, and its 1-year price return.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01
- `current_price`: float — from SKILL-D02

### Outputs
- `week_52_high`: float
- `week_52_low`: float
- `pct_from_52w_high`: float — % below 52-week high
- `pct_from_52w_low`: float — % above 52-week low
- `return_1y`: float — 1-year price return %
- `momentum_score`: float — 0 to 100

### Skill Dependencies
- SKILL-D01
- SKILL-D02

### Implementation Notes
- Score formula: weighted combination of proximity to 52W high and 1Y return
- Stocks within 10% of 52W high score 70–100 (bullish momentum)
- Stocks within 10% of 52W low score 0–30 (bearish momentum)

---

## SKILL-I06: Compute Volume Signal

| Property | Value |
|---|---|
| Skill ID | SKILL-I06 |
| Layer | Intelligence |
| Module | technical_module.py |
| Goal Applicability | G1, G2 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the relationship between current trading volume and average volume to determine whether a price move is confirmed by volume conviction.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01 (Close and Volume required)

### Outputs
- `avg_volume_30d`: float — 30-day average volume
- `current_volume`: float — latest day's volume
- `volume_ratio`: float — current volume / 30D average
- `volume_signal`: string — `high_conviction` (>1.5x avg), `normal`, `low_conviction` (<0.5x avg)
- `volume_price_signal`: string — `confirmed_breakout`, `confirmed_breakdown`, `unconfirmed`, or `neutral`

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Volume confirmation logic: rising price + high volume = confirmed; rising price + low volume = suspect
- Falling price + high volume = confirmed selling pressure
- Falling price + low volume = weak selling — potential recovery signal

---

## SKILL-I07: Compute Revenue Growth

| Property | Value |
|---|---|
| Skill ID | SKILL-I07 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes year-over-year and quarter-over-quarter revenue growth rates from financial statement data. Determines growth trajectory (accelerating, stable, or decelerating).

### Inputs
- `income_statement`: pandas DataFrame — from SKILL-D03

### Outputs
- `revenue_growth_yoy`: float — annual revenue growth %
- `revenue_growth_qoq`: float — quarterly revenue growth %
- `revenue_cagr_3y`: float — 3-year revenue CAGR %
- `growth_trajectory`: string — `accelerating`, `stable`, or `decelerating`
- `revenue_signal`: string — `green`, `amber`, or `red`

### Skill Dependencies
- SKILL-D03

### Implementation Notes
- Trajectory determined by comparing last 3 quarters of YoY growth rates
- Thresholds loaded from `thresholds.yaml`

---

## SKILL-I08: Compute Margin Trends

| Property | Value |
|---|---|
| Skill ID | SKILL-I08 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes gross margin, operating margin, and net profit margin for current and prior periods. Determines whether margins are expanding, stable, or compressing.

### Inputs
- `income_statement`: pandas DataFrame — from SKILL-D03

### Outputs
- `gross_margin`: float — current gross margin %
- `operating_margin`: float — current operating margin %
- `net_margin`: float — current net profit margin %
- `margin_trend`: string — `expanding`, `stable`, or `compressing`
- `margin_signal`: string — `green`, `amber`, or `red`

### Skill Dependencies
- SKILL-D03

### Implementation Notes
- Trend computed by comparing current margin to 4-quarter average
- Expanding = current > avg by > 1%; Compressing = current < avg by > 1%

---

## SKILL-I09: Compute Free Cash Flow & Growth

| Property | Value |
|---|---|
| Skill ID | SKILL-I09 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes Free Cash Flow (Operating Cash Flow minus CapEx), FCF growth rate, and FCF margin. Determines whether FCF is positive, growing, and consistent with reported earnings.

### Inputs
- `cash_flow`: pandas DataFrame — from SKILL-D03
- `income_statement`: pandas DataFrame — from SKILL-D03

### Outputs
- `fcf`: float — latest annual Free Cash Flow
- `fcf_growth_yoy`: float — FCF growth %
- `fcf_margin`: float — FCF as % of revenue
- `fcf_vs_net_income`: float — FCF / Net Income ratio (quality check)
- `fcf_signal`: string — `green`, `amber`, or `red`

### Skill Dependencies
- SKILL-D03

### Implementation Notes
- FCF = Operating Cash Flow - Capital Expenditure
- FCF/Net Income > 0.8 indicates high earnings quality
- Negative FCF for 2+ consecutive years = red signal regardless of reported profits

---

## SKILL-I10: Compute PEG Ratio

| Property | Value |
|---|---|
| Skill ID | SKILL-I10 |
| Layer | Intelligence |
| Module | valuation_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the Price/Earnings to Growth (PEG) ratio by dividing the trailing P/E ratio by the earnings growth rate. The single most useful valuation shortcut for growth stocks.

### Inputs
- `pe_ratio`: float — from SKILL-D04
- `eps_growth_rate`: float — from SKILL-I07 (revenue growth as proxy if EPS growth unavailable)

### Outputs
- `peg_ratio`: float — computed PEG
- `peg_signal`: string — `undervalued` (<1.0), `fair` (1.0–1.5), `overvalued` (>2.0)

### Skill Dependencies
- SKILL-D04
- SKILL-I07

### Implementation Notes
- If EPS growth is negative, PEG is not meaningful — flag as `N/A`
- Use 3-year EPS CAGR as growth rate where available for more stable result

---

## SKILL-I11: Compute P/E vs Sector Median

| Property | Value |
|---|---|
| Skill ID | SKILL-I11 |
| Layer | Intelligence |
| Module | valuation_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the stock's P/E ratio relative to the median P/E of its sector peers. Determines whether the stock is trading at a premium, discount, or in-line with its sector.

### Inputs
- `pe_ratio`: float — from SKILL-D04
- `peer_comparison`: pandas DataFrame — from SKILL-D05 (peer P/E ratios)
- `sector`: string — from portfolio config

### Outputs
- `sector_median_pe`: float
- `pe_premium_discount_pct`: float — % premium (+) or discount (-) vs sector median
- `pe_vs_sector_signal`: string — `discount` (<-15%), `inline` (±15%), `premium` (>15%)

### Skill Dependencies
- SKILL-D04
- SKILL-D05

### Implementation Notes
- Sector median computed from peer_comparison DataFrame
- If fewer than 3 peers available, flag as insufficient data

---

## SKILL-I12: Compute EV/EBITDA

| Property | Value |
|---|---|
| Skill ID | SKILL-I12 |
| Layer | Intelligence |
| Module | valuation_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes Enterprise Value to EBITDA ratio. More reliable than P/E for comparing companies with different capital structures.

### Inputs
- `ev_ebitda`: float — from SKILL-D04 (yfinance) or SKILL-D05 (Screener.in)
- `sector`: string — for sector context

### Outputs
- `ev_ebitda_value`: float
- `ev_ebitda_signal`: string — `green` (<8), `amber` (8–15), `red` (>20)

### Skill Dependencies
- SKILL-D04
- SKILL-D05

### Implementation Notes
- Use Screener.in value if yfinance value is unavailable
- Flag as N/A if neither source has data

---

## SKILL-I13: Compute ROIC

| Property | Value |
|---|---|
| Skill ID | SKILL-I13 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes Return on Invested Capital (ROIC). Measures how efficiently management deploys capital. ROIC above cost of capital (~10%) indicates value creation.

### Inputs
- `income_statement`: pandas DataFrame — from SKILL-D03
- `balance_sheet`: pandas DataFrame — from SKILL-D03
- `roic_screener`: float — from SKILL-D05 (used if cannot compute from statements)

### Outputs
- `roic`: float — ROIC %
- `roic_signal`: string — `green` (>12%), `amber` (8–12%), `red` (<8%)

### Skill Dependencies
- SKILL-D03
- SKILL-D05

### Implementation Notes
- ROIC = NOPAT / Invested Capital
- NOPAT = Operating Income × (1 - Tax Rate)
- Invested Capital = Total Assets - Current Liabilities - Cash
- Use Screener.in ROIC directly if financial statement computation is not possible

---

## SKILL-I14: Compute Relative Strength vs Sector

| Property | Value |
|---|---|
| Skill ID | SKILL-I14 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | G2, G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Measures whether a stock is outperforming or underperforming its sector index over 1-month, 3-month, and 6-month periods.

### Inputs
- `price_df`: pandas DataFrame — from SKILL-D01
- `sector_index_df`: pandas DataFrame — from SKILL-D12

### Outputs
- `rs_1m`: float — stock return vs sector return over 1 month
- `rs_3m`: float — stock return vs sector return over 3 months
- `rs_6m`: float — stock return vs sector return over 6 months
- `rs_signal`: string — `outperforming`, `inline`, or `underperforming`

### Skill Dependencies
- SKILL-D01
- SKILL-D12

---

## SKILL-I15: Compute Earnings Surprise %

| Property | Value |
|---|---|
| Skill ID | SKILL-I15 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes earnings surprise percentage for the last 4 quarters by comparing actual EPS to analyst consensus estimates.

### Inputs
- `actual_eps`: list of floats — last 4 quarters actual EPS from SKILL-D03
- `estimated_eps`: list of floats — analyst estimates from SKILL-D04

### Outputs
- `surprise_pct_list`: list of floats — surprise % per quarter
- `avg_surprise_pct`: float — average over last 4 quarters
- `surprise_signal`: string — `consistent_beat` (>+5% avg), `inline`, `consistent_miss` (<-5% avg)

### Skill Dependencies
- SKILL-D03
- SKILL-D04

### Implementation Notes
- If analyst estimates unavailable, flag as N/A — do not penalise score
- Consecutive misses (2+) should trigger amber flag in fundamental scorecard

---

## SKILL-I16: Compute Earnings Estimate Revisions

| Property | Value |
|---|---|
| Skill ID | SKILL-I16 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Detects whether analyst EPS estimates for the next quarter/year have been revised upward or downward compared to 30 days ago. Upward revisions are a leading indicator of improving fundamentals.

### Inputs
- `current_estimate`: float — current analyst consensus EPS estimate
- `prior_estimate`: float — estimate from 30 days ago (from cache)

### Outputs
- `revision_pct`: float — % change in estimate
- `revision_signal`: string — `upgraded` (>+3%), `stable`, `downgraded` (<-3%)

### Skill Dependencies
- SKILL-D04
- SKILL-D13 (to retrieve prior cached estimate)

---

## SKILL-I17: Compute Promoter Holding Signal

| Property | Value |
|---|---|
| Skill ID | SKILL-I17 |
| Layer | Intelligence |
| Module | fundamental_scoring_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Evaluates promoter holding percentage and quarter-on-quarter change as an India-specific fundamental signal. High and stable/rising promoter holding indicates founder confidence.

### Inputs
- `promoter_holding_pct`: float — from SKILL-D07
- `promoter_change_qoq`: float — from SKILL-D07
- `pledge_pct`: float — from SKILL-D08

### Outputs
- `promoter_signal`: string — `green`, `amber`, or `red`
- `promoter_score`: float — 0 to 100

### Signal Logic
- Green: holding > 50% AND stable/rising AND pledge < 10%
- Amber: holding 40–50% OR pledge 10–30% OR slight decline
- Red: holding < 40% OR pledge > 30% OR sharp decline (> 3% in a quarter)

### Skill Dependencies
- SKILL-D07
- SKILL-D08

---

## SKILL-I18: Score News Sentiment via Claude AI

| Property | Value |
|---|---|
| Skill ID | SKILL-I18 |
| Layer | Intelligence |
| Module | sentiment_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | 12 hours |
| AI Dependency | Yes — Claude claude-sonnet-4-5 |
| External Dependency | Anthropic API |

### Description
Sends a batch of news headlines and summaries for a given stock to Claude AI and receives a structured sentiment assessment. Returns an aggregate sentiment score, key themes, and risk flags.

### Inputs
- `headlines`: list of dicts — from SKILL-D09 and SKILL-D10
- `company_name`: string
- `ticker`: string

### Outputs
- `sentiment_score`: float — 0 to 100 (higher = more positive)
- `sentiment_label`: string — `positive`, `neutral`, or `negative`
- `key_positive_themes`: list of strings — main positive signals identified
- `key_negative_themes`: list of strings — main risk signals identified
- `confidence`: string — `high`, `medium`, or `low` (based on number of headlines)

### Claude Prompt Template
```
You are a financial analyst for Indian stock markets. 
Analyse the following {N} news headlines about {company_name} ({ticker}).
Return ONLY a JSON object with these fields:
- sentiment_score: integer 0-100
- sentiment_label: "positive", "neutral", or "negative"
- key_positive_themes: list of up to 3 strings
- key_negative_themes: list of up to 3 strings
- confidence: "high", "medium", or "low"

Headlines:
{headlines_text}
```

### Skill Dependencies
- SKILL-D09
- SKILL-D10

### Implementation Notes
- Model: `claude-sonnet-4-5`
- Always request JSON output — parse with `json.loads()`
- Implement retry with exponential backoff for 529 overloaded errors (max 3 retries)
- Cache results for 12 hours to minimise API costs
- If fewer than 3 headlines available, set confidence to `low`
- Batch all headlines for a stock into one API call — do not call per headline

---

## SKILL-I19: Compute Insider Activity Signal

| Property | Value |
|---|---|
| Skill ID | SKILL-I19 |
| Layer | Intelligence |
| Module | sentiment_module.py |
| Goal Applicability | G1, G2 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Analyses insider buying and selling disclosures from NSE/BSE announcements to determine net insider sentiment over the last 90 days.

### Inputs
- `insider_disclosures`: list — from SKILL-D10
- `days_lookback`: int — default 90

### Outputs
- `net_insider_direction`: string — `buying`, `selling`, or `neutral`
- `insider_buy_value`: float — total value of insider purchases
- `insider_sell_value`: float — total value of insider sales
- `insider_signal`: string — `green` (net buying), `amber` (neutral), `red` (heavy selling)

### Skill Dependencies
- SKILL-D10

### Implementation Notes
- Exclude routine ESOP exercises from sell calculations — these are not discretionary selling
- Weight recent transactions (last 30 days) more heavily than older ones

---

## SKILL-I20: Compute Institutional Ownership Change

| Property | Value |
|---|---|
| Skill ID | SKILL-I20 |
| Layer | Intelligence |
| Module | sentiment_module.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Evaluates the direction of change in FII, DII, and mutual fund holdings quarter-on-quarter. Increasing institutional ownership is a positive conviction signal.

### Inputs
- `fii_change_qoq`: float — from SKILL-D07
- `dii_change_qoq`: float — from SKILL-D07

### Outputs
- `institutional_direction`: string — `accumulating`, `stable`, or `distributing`
- `institutional_signal`: string — `green`, `amber`, or `red`

### Skill Dependencies
- SKILL-D07

---

## SKILL-I21: Compute Fundamental Scorecard Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I21 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Aggregates sub-scores from all fundamental metrics into a single Fundamental Scorecard Score (0–100). Weights loaded from `scorecard_weights.yaml`.

### Inputs
- `revenue_signal`: string — from SKILL-I07
- `margin_signal`: string — from SKILL-I08
- `fcf_signal`: string — from SKILL-I09
- `roic_signal`: string — from SKILL-I13
- `promoter_signal`: string — from SKILL-I17
- `surprise_signal`: string — from SKILL-I15

### Outputs
- `fundamental_score`: float — 0 to 100
- `fundamental_grade`: string — `Strong`, `Moderate`, or `Weak`
- `fundamental_breakdown`: dict — individual metric sub-scores

### Skill Dependencies
- SKILL-I07, I08, I09, I13, I15, I17

### Signal to Sub-Score Mapping
- `green` → 80 points
- `amber` → 50 points
- `red` → 15 points
- `N/A` → excluded from average (not penalised)

---

## SKILL-I22: Compute Technical Scorecard Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I22 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Aggregates technical indicator signals into a single Technical Scorecard Score (0–100).

### Inputs
- `trend_signal`: string — from SKILL-I01
- `rsi_signal`: string — from SKILL-I02
- `macd_signal`: string — from SKILL-I03
- `momentum_score`: float — from SKILL-I05
- `volume_signal`: string — from SKILL-I06

### Outputs
- `technical_score`: float — 0 to 100
- `technical_grade`: string — `Bullish`, `Neutral`, or `Bearish`
- `technical_breakdown`: dict — individual metric sub-scores

### Skill Dependencies
- SKILL-I01, I02, I03, I05, I06

---

## SKILL-I23: Compute Valuation Scorecard Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I23 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Aggregates valuation metric signals into a single Valuation Scorecard Score (0–100). Higher score = more attractive valuation.

### Inputs
- `peg_signal`: string — from SKILL-I10
- `pe_vs_sector_signal`: string — from SKILL-I11
- `ev_ebitda_signal`: string — from SKILL-I12

### Outputs
- `valuation_score`: float — 0 to 100
- `valuation_grade`: string — `Undervalued`, `Fair`, or `Overvalued`
- `valuation_breakdown`: dict

### Skill Dependencies
- SKILL-I10, I11, I12

---

## SKILL-I24: Compute Risk Scorecard Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I24 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Aggregates risk signals into a single Risk Scorecard Score (0–100). Higher score = lower risk.

### Inputs
- `beta`: float — from SKILL-I04
- `stop_loss_proximity_pct`: float — from SKILL-I31
- `portfolio_concentration_pct`: float — from portfolio config
- `debt_equity`: float — from SKILL-D03
- `pledge_pct`: float — from SKILL-D08

### Outputs
- `risk_score`: float — 0 to 100 (higher = lower risk)
- `risk_grade`: string — `Low`, `Moderate`, or `High`
- `risk_breakdown`: dict

### Skill Dependencies
- SKILL-I04, I31, D03, D08

---

## SKILL-I25: Compute Sentiment Scorecard Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I25 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Aggregates sentiment signals into a single Sentiment Scorecard Score (0–100).

### Inputs
- `sentiment_score`: float — from SKILL-I18
- `insider_signal`: string — from SKILL-I19
- `institutional_signal`: string — from SKILL-I20
- `analyst_recommendation`: string — from SKILL-D04

### Outputs
- `sentiment_scorecard_score`: float — 0 to 100
- `sentiment_grade`: string — `Positive`, `Mixed`, or `Negative`
- `sentiment_breakdown`: dict

### Skill Dependencies
- SKILL-I18, I19, I20, D04

---

## SKILL-I26: Compute Overall Stock Score

| Property | Value |
|---|---|
| Skill ID | SKILL-I26 |
| Layer | Intelligence |
| Module | scorecard_aggregator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Combines all five scorecard scores into a single Overall Stock Score (0–100) using configurable weights from `scorecard_weights.yaml`. Maps score to a recommendation action.

### Inputs
- `fundamental_score`: float — from SKILL-I21
- `technical_score`: float — from SKILL-I22
- `valuation_score`: float — from SKILL-I23
- `risk_score`: float — from SKILL-I24
- `sentiment_scorecard_score`: float — from SKILL-I25

### Outputs
- `overall_score`: float — 0 to 100
- `recommendation`: string — `Strong Buy`, `Buy`, `Hold`, `Reduce`, or `Exit`
- `score_breakdown`: dict — all five scorecard scores and weights

### Default Weights
- Fundamental: 30%
- Valuation: 25%
- Technical: 20%
- Sentiment: 15%
- Risk: 10%

### Skill Dependencies
- SKILL-I21, I22, I23, I24, I25

---

## SKILL-I27: Compute Inter-Stock Correlation Matrix

| Property | Value |
|---|---|
| Skill ID | SKILL-I27 |
| Layer | Intelligence |
| Module | portfolio_analytics_module.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes a correlation matrix of daily returns across all portfolio holdings. Identifies pairs of highly correlated stocks that reduce diversification benefit.

### Inputs
- `price_data`: dict of pandas DataFrames — all holdings price history from SKILL-D01

### Outputs
- `correlation_matrix`: pandas DataFrame — N×N matrix of pairwise correlations
- `high_correlation_pairs`: list of tuples — pairs with correlation > 0.7
- `avg_portfolio_correlation`: float — average pairwise correlation

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Computed using `pandas.DataFrame.corr()` on daily returns
- Correlation > 0.7 between two holdings = diversification concern — flag for review

---

## SKILL-I28: Compute Sector Allocation

| Property | Value |
|---|---|
| Skill ID | SKILL-I28 |
| Layer | Intelligence |
| Module | portfolio_analytics_module.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the current sector allocation of the portfolio as a percentage of total portfolio value. Compares against target allocations from `goals.yaml` and identifies sector drift.

### Inputs
- `holdings`: list — from portfolio.db
- `current_prices`: dict — from SKILL-D02

### Outputs
- `sector_allocation`: dict — current % per sector
- `target_allocation`: dict — from goals.yaml
- `sector_drift`: dict — current minus target per sector
- `overweight_sectors`: list — sectors exceeding target by > drift threshold
- `underweight_sectors`: list — sectors below target by > drift threshold

### Skill Dependencies
- SKILL-D02

---

## SKILL-I29: Compute Portfolio Beta

| Property | Value |
|---|---|
| Skill ID | SKILL-I29 |
| Layer | Intelligence |
| Module | portfolio_analytics_module.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the weighted average Beta of the entire portfolio relative to Nifty 50 using individual stock betas and portfolio weights.

### Inputs
- `holdings`: list — from portfolio.db
- `betas`: dict — individual stock betas from SKILL-I04
- `current_prices`: dict — from SKILL-D02

### Outputs
- `portfolio_beta`: float — weighted average portfolio beta
- `beta_signal`: string — `defensive` (<0.8), `market_neutral` (0.8–1.2), `aggressive` (>1.2)

### Skill Dependencies
- SKILL-I04
- SKILL-D02

---

## SKILL-I30: Compute Portfolio Sharpe Ratio

| Property | Value |
|---|---|
| Skill ID | SKILL-I30 |
| Layer | Intelligence |
| Module | portfolio_analytics_module.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes the portfolio Sharpe Ratio — risk-adjusted return — using portfolio daily returns, standard deviation, and the risk-free rate (RBI repo rate from system.yaml).

### Inputs
- `portfolio_returns`: pandas Series — daily portfolio return history from portfolio.db
- `risk_free_rate`: float — from system.yaml

### Outputs
- `sharpe_ratio`: float
- `sharpe_signal`: string — `excellent` (>1.5), `good` (1.0–1.5), `poor` (<1.0)
- `portfolio_volatility`: float — annualised standard deviation of returns

### Skill Dependencies
- SKILL-D01

### Implementation Notes
- Annualised Sharpe = (Mean Daily Return - Daily Risk Free Rate) / Std Dev × √252
- Uses `scipy.stats` and `numpy` for computation

---

## SKILL-I31: Compute Stop-Loss Proximity

| Property | Value |
|---|---|
| Skill ID | SKILL-I31 |
| Layer | Intelligence |
| Module | risk_module.py |
| Goal Applicability | G1, G3 |
| Status | Active |
| Cache TTL | N/A (computed) |
| AI Dependency | No |
| External Dependency | None |

### Description
Computes ATR-based stop-loss price for each holding. ATR (Average True Range) adapts the stop-loss to each stock's actual volatility rather than a fixed percentage. Falls back to fixed percentage if price data is insufficient.

### ATR Formula
```
True Range     = MAX(High-Low, |High-PrevClose|, |Low-PrevClose|)
ATR            = 14-day Wilder EMA of True Range
Stop-Loss Price = Buy Price - (ATR Multiplier × ATR)
```

### Inputs
- `current_price`: float — current market price (from SKILL-D02)
- `buy_price`: float — weighted average purchase price from portfolio
- `price_df`: pd.DataFrame — OHLCV history for ATR computation (from SKILL-D01)
- `stop_loss_pct`: float — fallback fixed % (default 12.0)
- `config`: dict — for ATR period (14), multiplier (2.0), warning threshold (3%)

### Outputs
- `stop_loss_price`: float — computed stop-loss level
- `stop_loss_method`: str — 'atr' or 'fixed_pct'
- `atr_value`: float | None — computed ATR
- `atr_multiplier`: float — multiplier used
- `equivalent_stop_pct`: float — ATR stop as % of buy price
- `current_drawdown_pct`: float — % change from buy price
- `proximity_to_stop_pct`: float — gap between current price and stop-loss
- `stop_loss_signal`: str — 'safe' | 'warning' | 'breached'

### Signal Logic
- `current_price ≤ stop_loss_price` → breached 🔴
- `proximity_to_stop_pct ≤ 3%` → warning 🟠
- `proximity_to_stop_pct > 3%` → safe 🟢

### ATR Sanity Check
ATR-based stop must fall between 3% and 30% below buy price.
Outside this range → fallback to fixed percentage.

### Skill Dependencies
- SKILL-D01 (price history for ATR)
- SKILL-D02 (current price)

---
---

# ACTION LAYER SKILLS (A-Series)

---

## SKILL-A01: Generate Stock Recommendation

| Property | Value |
|---|---|
| Skill ID | SKILL-A01 |
| Layer | Action |
| Module | recommendation_engine.py |
| Goal Applicability | G1 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Applies the three-layer decision matrix to the overall stock score and individual scorecard signals to generate a final recommendation for an existing portfolio holding.

### Inputs
- `overall_score`: float — from SKILL-I26
- `fundamental_grade`: string — from SKILL-I21
- `technical_grade`: string — from SKILL-I22
- `sentiment_grade`: string — from SKILL-I25
- `stop_loss_signal`: string — from SKILL-I31
- `thesis_intact`: bool — from portfolio config

### Outputs
- `recommendation`: string — `Strong Buy`, `Buy`, `Hold`, `Reduce`, or `Exit`
- `recommendation_rationale`: string — plain English explanation of recommendation
- `supporting_signals`: list — key signals driving the recommendation
- `contradicting_signals`: list — signals going against the recommendation
- `recommended_action`: string — specific action (e.g. `Add 20 shares`, `Trim to 5% weight`, `Exit fully`)

### Skill Dependencies
- SKILL-I21, I22, I25, I26, I31

### Implementation Notes
- Decision matrix logic loaded from `thresholds.yaml` and `scorecard_weights.yaml`
- If thesis_intact is False → override to `Reduce` or `Exit` regardless of score
- If stop_loss_signal is `breached` → override to `Exit`

---

## SKILL-A02: Screen Stock Universe

| Property | Value |
|---|---|
| Skill ID | SKILL-A02 |
| Layer | Action |
| Module | discovery_engine.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Applies configurable screening filters to the Nifty 500 universe to produce a shortlist of candidate stocks for detailed evaluation. Eliminates clearly unsuitable stocks before running expensive scoring.

### Inputs
- `nifty500_tickers`: list — full Nifty 500 ticker list
- `screening_filters`: dict — from goals.yaml (min market cap, min revenue growth, FCF positive etc.)

### Outputs
- `candidate_tickers`: list — stocks passing all screening filters
- `eliminated_count`: int — stocks eliminated by screening
- `screen_summary`: dict — count eliminated per filter

### Default Screening Filters (from goals.yaml)
- Market cap > ₹1,000 crore
- Revenue growth (YoY) > 5%
- FCF positive (latest year)
- Not already in existing portfolio
- Avg daily volume > 100,000 shares

### Skill Dependencies
- SKILL-D03, SKILL-D04

---

## SKILL-A03: Evaluate New Stock Candidate

| Property | Value |
|---|---|
| Skill ID | SKILL-A03 |
| Layer | Action |
| Module | discovery_engine.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Runs the full scoring pipeline (all 5 scorecards) on a new stock candidate that has passed the screening filter. Also checks portfolio fit — correlation with existing holdings and sector allocation impact.

### Inputs
- `ticker`: string — candidate stock ticker
- `existing_portfolio`: list — current holdings for correlation check
- `current_sector_allocation`: dict — from SKILL-I28

### Outputs
- `overall_score`: float
- `all_scorecard_scores`: dict
- `recommendation`: string
- `portfolio_correlation_impact`: string — `diversifying`, `neutral`, or `correlated`
- `sector_allocation_impact`: string — `fills gap`, `neutral`, or `adds overweight`
- `sharpe_improvement`: bool — would adding this stock improve portfolio Sharpe ratio

### Skill Dependencies
- All I-series scoring skills
- SKILL-I27, SKILL-I28, SKILL-I30

---

## SKILL-A04: Rank Discovery Candidates

| Property | Value |
|---|---|
| Skill ID | SKILL-A04 |
| Layer | Action |
| Module | discovery_engine.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Ranks all evaluated new stock candidates by overall score, adjusted for portfolio fit. Produces a prioritised list of new investment recommendations.

### Inputs
- `evaluated_candidates`: list of dicts — from SKILL-A03
- `portfolio_fit_weight`: float — how much to weight portfolio fit vs raw score (default: 20%)

### Outputs
- `ranked_candidates`: list of dicts — sorted by adjusted score descending
- `top_recommendations`: list — top 5 candidates with rationale

### Skill Dependencies
- SKILL-A03

---

## SKILL-A05: Detect Sector Allocation Drift

| Property | Value |
|---|---|
| Skill ID | SKILL-A05 |
| Layer | Action |
| Module | optimisation_engine.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Compares current sector allocation against target allocation from `goals.yaml`. Flags sectors that have drifted beyond the configured threshold and triggers rebalancing consideration.

### Inputs
- `sector_drift`: dict — from SKILL-I28
- `drift_threshold`: float — from goals.yaml (default: 5%)

### Outputs
- `drift_detected`: bool
- `sectors_to_trim`: list — overweight sectors
- `sectors_to_add`: list — underweight sectors
- `rebalancing_urgency`: string — `immediate` (>10% drift), `soon` (5–10%), `monitor` (<5%)

### Skill Dependencies
- SKILL-I28

---

## SKILL-A06: Generate Portfolio Rebalancing Plan

| Property | Value |
|---|---|
| Skill ID | SKILL-A06 |
| Layer | Action |
| Module | optimisation_engine.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Generates a specific, actionable rebalancing plan — which stocks to trim, which to add to, and which new candidates to initiate — to bring the portfolio back to target allocations while improving Sharpe ratio.

### Inputs
- `sectors_to_trim`: list — from SKILL-A05
- `sectors_to_add`: list — from SKILL-A05
- `ranked_candidates`: list — from SKILL-A04
- `holdings`: list — from portfolio.db
- `current_prices`: dict — from SKILL-D02

### Outputs
- `rebalancing_plan`: list of dicts — each containing: action (`trim`/`add`/`initiate`/`exit`), ticker, current weight, target weight, recommended trade size
- `estimated_portfolio_beta_after`: float
- `estimated_sharpe_after`: float

### Skill Dependencies
- SKILL-A05, SKILL-A04, SKILL-I30

---

## SKILL-A07: Detect Stop-Loss Breach

| Property | Value |
|---|---|
| Skill ID | SKILL-A07 |
| Layer | Action |
| Module | alert_manager.py |
| Goal Applicability | G1, G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Monitors all portfolio holdings for stop-loss breaches. Triggers an immediate exit alert when current price falls below the configured stop-loss level.

### Inputs
- `stop_loss_signals`: dict — from SKILL-I31 for all holdings

### Outputs
- `breached_tickers`: list — tickers where stop-loss is breached
- `warning_tickers`: list — tickers within 3% of stop-loss
- `alerts`: list — alert objects for SKILL-A09

### Skill Dependencies
- SKILL-I31

---

## SKILL-A08: Detect Thesis Integrity Change

| Property | Value |
|---|---|
| Skill ID | SKILL-A08 |
| Layer | Action |
| Module | alert_manager.py |
| Goal Applicability | G1, G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Monitors for conditions that may indicate the original investment thesis for a holding has changed or broken. Flags the holding for user review when multiple fundamental signals deteriorate.

### Inputs
- `fundamental_scores`: dict — current and prior period from SKILL-I21
- `thesis_intact`: bool — from portfolio config (user-managed flag)
- `revenue_signal`: string — from SKILL-I07
- `fcf_signal`: string — from SKILL-I09

### Outputs
- `thesis_risk_tickers`: list — holdings showing thesis deterioration signals
- `thesis_broken_tickers`: list — holdings where user has manually flagged thesis as broken
- `alerts`: list — alert objects for SKILL-A09

### Skill Dependencies
- SKILL-I21, SKILL-I07, SKILL-I09

---

## SKILL-A09: Generate Alert

| Property | Value |
|---|---|
| Skill ID | SKILL-A09 |
| Layer | Action |
| Module | alert_manager.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Receives alert triggers from all other action skills and writes structured alert records to the `alerts_log` table in `portfolio.db`. Alerts are surfaced in the Presentation Layer.

### Inputs
- `alert_type`: string — `stop_loss_breach`, `stop_loss_warning`, `thesis_risk`, `sector_drift`, `sentiment_deterioration`, `rebalancing_required`
- `ticker`: string (optional)
- `message`: string
- `urgency`: string — `high`, `medium`, or `low`

### Outputs
- `alert_id`: string — unique alert identifier
- `alert_record`: dict — stored to alerts_log table

### Skill Dependencies
- None (foundational action skill)

---

## SKILL-A10: Orchestrate G1 Workflow

| Property | Value |
|---|---|
| Skill ID | SKILL-A10 |
| Layer | Action |
| Module | orchestrator.py |
| Goal Applicability | G1 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Orchestrates the complete G1 workflow — existing portfolio recommendation — by chaining all required skills in the correct dependency order for each holding in the portfolio.

### Workflow Sequence
1. Load portfolio from `portfolio.db`
2. SKILL-D02 → current prices
3. SKILL-D01 → price history
4. SKILL-D03 → financial statements
5. SKILL-D04 → ratios
6. SKILL-D05 → Screener.in data
7. SKILL-D07, D08 → shareholding & pledge
8. SKILL-D09, D10 → news & announcements
9. SKILL-I01 to I06 → technical indicators
10. SKILL-I07 to I17 → fundamental metrics
11. SKILL-I18 to I20 → sentiment signals
12. SKILL-I21 to I26 → scorecards & overall score
13. SKILL-I31 → stop-loss proximity
14. SKILL-A01 → recommendation
15. SKILL-A07, A08 → alert detection
16. SKILL-A09 → alert generation
17. Write results to `portfolio.db`

### Skill Dependencies
- All D and I series skills
- SKILL-A01, A07, A08, A09

---

## SKILL-A11: Orchestrate G2 Workflow

| Property | Value |
|---|---|
| Skill ID | SKILL-A11 |
| Layer | Action |
| Module | orchestrator.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Orchestrates the G2 new stock discovery workflow — screening the Nifty 500 universe and producing a ranked list of investment candidates.

### Workflow Sequence
1. Load Nifty 500 ticker list
2. SKILL-A02 → screening filter (shortlist candidates)
3. For each candidate: run all D-series data fetches
4. For each candidate: run all I-series scoring skills
5. SKILL-A03 → evaluate portfolio fit per candidate
6. SKILL-A04 → rank all candidates
7. Write ranked results to `portfolio.db`

### Skill Dependencies
- SKILL-A02, A03, A04 and all supporting D/I skills

---

## SKILL-A12: Orchestrate G3 Workflow

| Property | Value |
|---|---|
| Skill ID | SKILL-A12 |
| Layer | Action |
| Module | orchestrator.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Orchestrates the G3 portfolio optimisation workflow — detecting drift, running correlation and risk analysis, and generating a rebalancing plan.

### Workflow Sequence
1. Load portfolio from `portfolio.db`
2. SKILL-I27 → correlation matrix
3. SKILL-I28 → sector allocation
4. SKILL-I29 → portfolio beta
5. SKILL-I30 → Sharpe ratio
6. SKILL-A05 → sector drift detection
7. Pull G2 results (ranked candidates) from `portfolio.db`
8. SKILL-A06 → rebalancing plan
9. SKILL-A09 → generate rebalancing alerts
10. Write plan to `rebalancing_log` in `portfolio.db`

### Skill Dependencies
- SKILL-I27, I28, I29, I30, A05, A06, A09

---

## SKILL-A13: Schedule Automated Refresh

| Property | Value |
|---|---|
| Skill ID | SKILL-A13 |
| Layer | Action |
| Module | orchestrator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None |

### Description
Uses APScheduler to schedule automated execution of all three goal workflows on configurable cadences. Runs as a background process when the Streamlit app is running.

### Schedule Configuration (from goals.yaml)

| Job | Cadence | Workflow Triggered |
|---|---|---|
| Daily refresh | Weekdays at 4:30 PM IST (after market close) | G1 full run |
| Weekly discovery | Every Monday at 6:00 AM IST | G2 full run |
| Monthly fundamentals | 1st of every month at 6:00 AM | G1 fundamentals refresh |
| Quarterly optimisation | 1st of Jan, Apr, Jul, Oct | G3 full run |

### Skill Dependencies
- SKILL-A10, A11, A12

---
---

# PRESENTATION LAYER SKILLS (P-Series)

---

## SKILL-P01: Render Portfolio Overview Dashboard

| Property | Value |
|---|---|
| Skill ID | SKILL-P01 |
| Layer | Presentation |
| Module | dashboard.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | Streamlit |

### Description
Renders the main portfolio overview dashboard as the home screen of the Streamlit application. Shows top-level portfolio health, individual stock scores, active alerts, and goal status.

### Inputs
- All scorecard results from `portfolio.db`
- Active alerts from `alerts_log`
- Portfolio valuation from SKILL-D02

### Dashboard Sections
1. **Portfolio Summary Bar** — Total value, day change %, overall portfolio health score, benchmark comparison
2. **Active Alerts Panel** — High urgency alerts at the top; colour-coded by urgency
3. **Holdings Scorecard Table** — All stocks with overall score, recommendation, and traffic light indicators per scorecard
4. **Goal Status Indicators** — G1, G2, G3 last run timestamp and status
5. **Top Recommendations** — Top 3 actions to take across all goals

### Skill Dependencies
- SKILL-A10, A11, A12 (workflow results)

---

## SKILL-P02: Render Stock Detail & Scorecard View

| Property | Value |
|---|---|
| Skill ID | SKILL-P02 |
| Layer | Presentation |
| Module | stock_detail_view.py |
| Goal Applicability | G1 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | Streamlit |

### Description
Renders a detailed drilldown view for a selected stock showing all 32 metrics, 5 scorecard breakdowns, price chart with MA overlays, and the full recommendation with rationale.

### Inputs
- `ticker`: string — selected stock
- All metric and scorecard results from `portfolio.db`

### View Sections
1. **Price Chart** — 1-year price chart with 50D and 200D MA overlays, volume bars
2. **Overall Score Gauge** — Visual 0–100 score dial with recommendation label
3. **Scorecard Breakdown** — 5 scorecard cards with individual metric sub-scores
4. **Key Metrics Table** — All 32 metrics with current value, signal, and threshold reference
5. **Recommendation Panel** — Action, rationale, supporting and contradicting signals
6. **News Sentiment** — Last 30 days headlines with sentiment label
7. **Thesis Note** — Current thesis text with intact/broken flag and edit capability

### Skill Dependencies
- SKILL-A01 (recommendation)

---

## SKILL-P03: Render Discovery Candidates View

| Property | Value |
|---|---|
| Skill ID | SKILL-P03 |
| Layer | Presentation |
| Module | stock_detail_view.py |
| Goal Applicability | G2 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | Streamlit |

### Description
Renders the G2 new stock discovery view — a ranked table of investment candidates with scores, portfolio fit indicators, and the ability to drilldown into any candidate.

### View Sections
1. **Candidate Ranking Table** — Ranked by adjusted score; columns: ticker, sector, overall score, valuation grade, momentum grade, portfolio fit, sector impact
2. **Filters Panel** — Filter by sector, minimum score, portfolio fit type
3. **Candidate Drilldown** — Full scorecard detail for selected candidate (reuses SKILL-P02 layout)
4. **Add to Watchlist** — Button to move candidate to a watchlist in portfolio.db

### Skill Dependencies
- SKILL-A04 (ranked candidates)

---

## SKILL-P04: Render Portfolio Optimisation View

| Property | Value |
|---|---|
| Skill ID | SKILL-P04 |
| Layer | Presentation |
| Module | portfolio_view.py |
| Goal Applicability | G3 |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | Streamlit |

### Description
Renders the G3 portfolio optimisation view — sector allocation charts, correlation heatmap, risk metrics, and the actionable rebalancing plan.

### View Sections
1. **Sector Allocation Chart** — Current vs target allocation (bar chart with drift indicators)
2. **Correlation Heatmap** — Interactive N×N heatmap of all holdings
3. **Portfolio Risk Metrics** — Portfolio Beta, Sharpe Ratio, Max Drawdown, Volatility
4. **Rebalancing Plan Table** — Specific actions: ticker, action type, current weight, target weight, recommended trade size
5. **Before/After Metrics** — Estimated portfolio Beta and Sharpe improvement after rebalancing

### Skill Dependencies
- SKILL-A06 (rebalancing plan)
- SKILL-I27, I28, I29, I30

---

## SKILL-P05: Render Alerts Panel

| Property | Value |
|---|---|
| Skill ID | SKILL-P05 |
| Layer | Presentation |
| Module | dashboard.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | Streamlit |

### Description
Renders a dedicated alerts panel showing all active alerts sorted by urgency. Allows user to acknowledge and resolve alerts.

### View Sections
1. **High Urgency Alerts** — Stop-loss breaches, thesis broken (red)
2. **Medium Urgency Alerts** — Stop-loss warnings, sector drift > 10%, sentiment deterioration (amber)
3. **Low Urgency Alerts** — Rebalancing suggestions, monitoring flags (yellow)
4. **Alert History** — Resolved alerts log with timestamps

### Skill Dependencies
- SKILL-A09 (alert records)

---

## SKILL-P06: Generate PDF Portfolio Report

| Property | Value |
|---|---|
| Skill ID | SKILL-P06 |
| Layer | Presentation |
| Module | report_generator.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | fpdf2 |

### Description
Generates a formatted PDF portfolio report containing portfolio summary, individual stock scorecards, recommendations, and rebalancing plan. Saved to `data/exports/`.

### Inputs
- All scorecard and recommendation results from `portfolio.db`
- Report date and period

### Outputs
- PDF file: `data/exports/portfolio_report_{date}.pdf`

### Report Sections
1. Executive Summary — Portfolio value, benchmark comparison, top alerts
2. Individual Stock Pages — Score, recommendation, key metrics per holding
3. New Opportunities — Top G2 candidates summary
4. Rebalancing Plan — G3 actions table
5. Appendix — Metric definitions and threshold reference

### Skill Dependencies
- SKILL-A01, A04, A06

---

## SKILL-P07: Export Scores & Recommendations to Excel

| Property | Value |
|---|---|
| Skill ID | SKILL-P07 |
| Layer | Presentation |
| Module | export_manager.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | openpyxl |

### Description
Exports all scorecard scores, metric values, and recommendations to a structured Excel workbook with separate tabs per goal. Saved to `data/exports/`.

### Outputs
- Excel file: `data/exports/portfolio_scores_{date}.xlsx`
- Sheet 1: Portfolio Holdings — all metrics and scorecard scores
- Sheet 2: G2 Discovery Candidates — ranked list
- Sheet 3: G3 Rebalancing Plan — actions table
- Sheet 4: Alerts Log — all active alerts

### Skill Dependencies
- SKILL-A01, A04, A06

---

## SKILL-P08: Export Raw Data to CSV

| Property | Value |
|---|---|
| Skill ID | SKILL-P08 |
| Layer | Presentation |
| Module | export_manager.py |
| Goal Applicability | All |
| Status | Active |
| Cache TTL | N/A |
| AI Dependency | No |
| External Dependency | None (pandas built-in) |

### Description
Exports raw price history, financial statements, and metric data to CSV files for any selected stock. Useful for manual analysis or backup.

### Inputs
- `ticker`: string
- `data_type`: string — `price`, `financials`, `metrics`, or `all`

### Outputs
- CSV files: `data/exports/{ticker}_{data_type}_{date}.csv`

### Skill Dependencies
- SKILL-D01, D03

---

## Skill Status Summary

| Layer | Total Skills | Active | Planned | Disabled |
|---|---|---|---|---|
| Data (D-Series) | 14 | 14 | 0 | 0 |
| Intelligence (I-Series) | 31 | 31 | 0 | 0 |
| Action (A-Series) | 13 | 13 | 0 | 0 |
| Presentation (P-Series) | 8 | 8 | 0 | 0 |
| **Total** | **66** | **66** | **0** | **0** |

---

*SKILLS.md Status: v1.0 — Complete initial definition. Ready for build phase planning.*
*Next Step: Define build phases based on skill dependency chain.*