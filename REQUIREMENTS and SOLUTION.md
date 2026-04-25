# Portfolio Analysis System
## Baselined Requirements & Solution Outline
*Version 1.0 — Baseline*

---

## 1. Purpose & Goals

This system is designed to be an AI-powered, ongoing portfolio management tool with three distinct goals:

| # | Goal | Description |
|---|---|---|
| G1 | **Existing Portfolio Recommendations** | Analyse current stock holdings and generate actionable Buy / Hold / Reduce / Exit recommendations |
| G2 | **New Stock Discovery** | Screen and recommend new stocks not currently in the portfolio that are worth investing in |
| G3 | **Portfolio Balancing & Optimisation** | Ensure adequate, proportional distribution across dependent and independent sectors and companies to optimise risk-adjusted returns on an ongoing basis |

---

## 2. Decision Framework

Investment decisions are made through **three sequential layers**, each building on the previous:

### Layer 1 — The Business Filter (Fundamentals)
*"Is this a good business worth owning?"*
- First gate — if a company fails here, no other signal overrides it
- Covers revenue health, profitability, valuation, capital efficiency, and sector positioning

### Layer 2 — The Timing Filter (Technicals)
*"Is NOW the right time to act, and how much?"*
- Even great businesses can be bad trades if bought at the wrong time
- Covers price trends, momentum, volatility, and portfolio-level risk signals

### Layer 3 — The Conviction Filter (Sentiment & News)
*"How confident should I be, and is the market moving my way?"*
- Does not change direction of decision — influences position sizing and conviction level
- Covers analyst activity, insider signals, news sentiment, and thesis integrity

### Portfolio Layer (Goal 3 only)
*"Does this decision make my overall portfolio stronger and more resilient?"*
- Sector allocation drift, inter-stock correlation, portfolio beta, and Sharpe ratio impact

---

## 2a. Integrated Workflow Design

All three goals execute as **one cohesive block of work** in a single analysis run — not as independent separate runs. This ensures outputs are coherent and results flow naturally between goals.

### Single Run — Three Goals in Sequence

```
One Analysis Run
    │
    ├── Shared Data Fetch (once, reused across all goals)
    │       Price history, fundamentals, news, shareholding, macro
    │
    ├── G1: Score existing holdings → Recommendations
    │       Output: Per-stock scores, Buy/Hold/Reduce/Exit
    │
    ├── G2: Discover new candidates (informed by G1 output)
    │       Mode 1 — Gap Fill: Best stocks in underweight sectors
    │       Mode 2 — Peer Compare: Better performers in existing sectors
    │       Output: Ranked candidates with Switch/Distribute/Initiate tags
    │
    └── G3: Optimise portfolio (informed by G1 + G2 outputs)
            Sector drift detection + correlation + rebalancing plan
            Uses G2 candidates to fill identified gaps
            Output: Specific rebalancing actions
```

### Key Integration Rules
- **Data is fetched once and shared** — no repeated API calls across goals
- **G1 must complete before G2 starts** — discovery needs current holding scores
- **G2 must complete before G3 starts** — optimisation uses ranked candidates
- **One "Run Analysis" button** triggers the entire block
- **One unified result object** returned — all three goal outputs together

---

## 2b. G2 Discovery Strategy

G2 uses a **focused, portfolio-context-aware discovery strategy** rather than blanket universe screening. Two complementary modes run in sequence:

### Mode 1 — Gap Filling (G3-Aligned)
*"What sectors am I underweight in, and what are the best stocks in those sectors?"*

- Compare current sector allocation vs target allocation from `goals.yaml`
- Identify underweight sectors (current % significantly below target %)
- Screen the corresponding Nifty sector index for best scoring stocks
- Recommend **initiating new positions** to close sector gaps
- Directly serves G3 portfolio balancing objective

### Mode 2 — Sector Peer Comparison
*"Within sectors I already own, are there better performing stocks?"*

- For each sector currently held, identify peer stocks from the Nifty sector index
- Score peers using the same 5 scorecards as existing holdings
- Compare peer scores against existing holding scores in that sector
- Three recommendation outcomes:

| Outcome | Trigger | Action |
|---|---|---|
| **Switch** | Peer score > holding score by 15+ points | Consider replacing holding with peer |
| **Distribute** | Peer score within 15 points of holding | Consider splitting allocation across both |
| **Hold** | Holding scores higher than all peers | Confirm and hold existing position |

### Peer Universe Source
Nifty sector indices used as natural, pre-curated peer universes:
- Nifty IT → Technology sector peers
- Nifty Bank / Nifty Financial Services → Financial sector peers
- Nifty Pharma → Healthcare/Pharma peers
- Nifty Auto → Automobile sector peers
- Nifty FMCG → Consumer/FMCG peers
- Nifty Energy → Energy sector peers
- Nifty Metal → Metals sector peers

### Correlation Check
Before recommending any candidate, verify inter-stock correlation with existing holdings is below 0.7 — a highly correlated stock adds no diversification value regardless of its score.

### Switch Threshold Configuration (goals.yaml)
```yaml
g2_switch_score_gap: 15        # min score gap to recommend switch
g2_distribute_score_gap: 5     # min score gap to recommend distribute
g2_min_candidate_score: 45     # minimum overall score to be recommended
```

---

## 3. The Complete Metric Set (30 Metrics)

### Layer 1 — Fundamentals (10 Metrics)

| # | Metric | G1 | G2 | G3 |
|---|---|---|---|---|
| 1 | Revenue Growth (YoY) | ✅ | ✅ | ✅ |
| 2 | Free Cash Flow (FCF) | ✅ | ✅ | ✅ |
| 3 | Net Profit Margin Trend | ✅ | ✅ | ✅ |
| 4 | PEG Ratio | ✅ | ✅ | ✅ |
| 5 | P/E vs Sector Median | ✅ | ✅ | ✅ |
| 6 | Return on Invested Capital (ROIC) | ✅ | ✅ | ⚠️ |
| 7 | Debt-to-Equity Ratio | ✅ | ✅ | ✅ |
| 8 | Earnings Estimate Revisions | ⚠️ | ✅ | ⚠️ |
| 9 | Sector Classification (Cyclical / Defensive) | ❌ | ✅ | ✅ |
| 10 | Relative Strength vs Sector Peers | ⚠️ | ✅ | ✅ |
| 11 | Promoter Holding % & Trend *(India-specific)* | ✅ | ✅ | ✅ |
| 12 | Promoter Pledge % *(India-specific)* | ✅ | ✅ | ✅ |

### Layer 2 — Technicals (10 Metrics)

| # | Metric | G1 | G2 | G3 |
|---|---|---|---|---|
| 11 | Price vs 200-Day Moving Average | ✅ | ✅ | ✅ |
| 12 | RSI (14-day) | ✅ | ✅ | ✅ |
| 13 | MACD Crossover | ✅ | ✅ | ⚠️ |
| 14 | Volume vs Average Volume | ⚠️ | ✅ | ⚠️ |
| 15 | 52-Week Momentum Score | ⚠️ | ✅ | ✅ |
| 16 | Beta | ✅ | ✅ | ✅ |
| 17 | Portfolio Concentration % | ✅ | ❌ | ✅ |
| 18 | Sector Allocation Drift % | ❌ | ❌ | ✅ |
| 19 | Inter-Stock Correlation | ❌ | ✅ | ✅ |
| 20 | Stop-Loss Proximity (% from buy price) | ✅ | ❌ | ✅ |

### Layer 3 — Sentiment & News (10 Metrics)

| # | Metric | G1 | G2 | G3 |
|---|---|---|---|---|
| 21 | Earnings Surprise % (last 4 quarters) | ✅ | ✅ | ⚠️ |
| 22 | Insider Buying / Selling Activity | ✅ | ✅ | ⚠️ |
| 23 | Analyst Upgrades / Downgrades Trend | ✅ | ✅ | ⚠️ |
| 24 | Analyst Price Target Upside % | ✅ | ✅ | ⚠️ |
| 25 | News Sentiment Score (30-day) | ✅ | ✅ | ⚠️ |
| 26 | Institutional Ownership Change | ⚠️ | ✅ | ✅ |
| 27 | Thesis Integrity Flag | ✅ | ❌ | ✅ |
| 28 | Benchmark Relative Performance | ⚠️ | ❌ | ✅ |
| 29 | Portfolio Sharpe Ratio Impact | ❌ | ✅ | ✅ |
| 30 | Rebalancing Recommendation Flag | ❌ | ❌ | ✅ |

---

## 4. Metric Healthy Value Thresholds

### Fundamentals

| Metric | Healthy ✅ | Caution ⚠️ | Unhealthy 🔴 |
|---|---|---|---|
| Revenue Growth (YoY) | > 10% | 0–10% | Negative |
| Net Profit Margin | > 15% | 5–15% | < 5% |
| Free Cash Flow | Positive & growing | Positive but flat | Negative |
| Debt-to-Equity | < 0.5 | 0.5–1.5 | > 2.0 |
| ROIC | > 12% | 8–12% | < 8% |
| P/E vs Sector Median | Below median | At median | > 30% premium |
| PEG Ratio | < 1.0 | 1.0–1.5 | > 2.0 |
| EV/EBITDA | < 8 | 8–15 | > 20 |

### Technicals

| Metric | Bullish ✅ | Neutral ⚠️ | Bearish 🔴 |
|---|---|---|---|
| Price vs 200D MA | Above | Just crossed | Well below |
| RSI (14-day) | 40–60 or recovering from <30 | 60–70 | > 70 or < 30 in downtrend |
| MACD | Bullish crossover | Flat | Bearish crossover |
| Beta | 0.5–1.0 | 1.0–1.5 | > 1.5 |
| 52-Week Position | Within 10% of high | Mid-range | Near 52W low |
| Portfolio Concentration | < 5% | 5–10% | > 15% |

### Sentiment & News

| Metric | Positive ✅ | Neutral ⚠️ | Negative 🔴 |
|---|---|---|---|
| Promoter Holding % | > 50% & stable or rising | 40–50% | < 40% or falling sharply |
| Promoter Pledge % | < 10% | 10–30% | > 30% — serious red flag |
| Analyst Consensus Trend | Majority upgrades | Mixed / Hold | Majority downgrades |
| Analyst Price Target Upside | > 15% upside | 0–15% upside | Downside implied |
| Insider Activity | Net buying | Minimal | Heavy selling |
| News Sentiment Score | > 60% positive | 40–60% mixed | < 40% positive |
| Institutional Ownership | Increasing | Stable | Decreasing |

### Portfolio Level

| Metric | Healthy ✅ | Review ⚠️ | Concern 🔴 |
|---|---|---|---|
| Sharpe Ratio | > 1.5 | 1.0–1.5 | < 1.0 |
| Portfolio Beta | 0.8–1.2 | 1.2–1.5 | > 1.5 |
| Max Drawdown | < 10% | 10–20% | > 20% |
| Sector Concentration | No sector > 25% | 25–35% | > 40% |
| Number of Holdings | 10–20 | 5–10 or 20–30 | < 5 or > 40 |

---

## 5. Scorecard Architecture

Five scorecards feed into one Overall Stock Score:

| Scorecard | Metrics Included | Weight in Overall Score |
|---|---|---|
| Fundamental Health Score | Metrics 1–10 | 30% |
| Valuation Score | PEG, P/E vs Sector, EV/EBITDA | 25% |
| Technical Momentum Score | Metrics 11–16 | 20% |
| Sentiment & News Score | Metrics 21–26 | 15% |
| Risk Score | Beta, Concentration, Debt, Stop-loss | 10% |

**Overall Stock Score → Recommendation:**

| Score Range | Recommendation |
|---|---|
| 75–100 | Strong Buy / Add to position |
| 55–74 | Hold / Monitor closely |
| 35–54 | Reduce position / Review thesis |
| 0–34 | Exit / Stop-loss triggered |

---

## 6. Decision Matrix

### Per-Stock Decisions (Goals 1 & 2)

| Fundamentals | Technicals | Sentiment | G1 — Existing Stock | G2 — New Stock |
|---|---|---|---|---|
| ✅ Strong | ✅ Good | ✅ Positive | **Strong Buy — Add to position** | **Strong Buy — Initiate full position** |
| ✅ Strong | ✅ Good | ⚠️ Mixed | **Buy — Moderate add** | **Buy — Initiate moderate position** |
| ✅ Strong | ⚠️ Wait | ✅ Positive | **Hold — Set buy alert** | **Watchlist — Set entry alert** |
| ✅ Strong | ⚠️ Wait | ⚠️ Mixed | **Hold — Do not add yet** | **Watchlist — Monitor, don't enter** |
| ✅ Strong | 🔴 Poor | ⚠️ Mixed | **Hold — Tighten stop-loss** | **Avoid now — Revisit in 4–6 weeks** |
| ⚠️ Mixed | ✅ Good | ✅ Positive | **Hold — Review thesis before adding** | **Small speculative position only** |
| ⚠️ Mixed | ⚠️ Wait | ⚠️ Mixed | **Hold — Flag for quarterly review** | **Do not initiate** |
| ⚠️ Mixed | 🔴 Poor | 🔴 Negative | **Reduce position** | **Reject — Remove from watchlist** |
| 🔴 Weak | ✅ Good | ⚠️ Mixed | **Exit — Don't be fooled by bounce** | **Reject — Technicals don't fix bad fundamentals** |
| 🔴 Weak | Any | 🔴 Negative | **Exit immediately** | **Reject outright** |
| Any | 🔴 Poor | 🔴 Negative | **Do not add — Review stop-loss** | **Reject — Wait for stabilisation** |

### Portfolio-Level Decisions (Goal 3)

| Sector Drift | Correlation | Portfolio Beta | Sharpe Impact | Action |
|---|---|---|---|---|
| Within ±5% target | Low | 0.8–1.2 | Stable / improving | **No action — Portfolio healthy** |
| One sector > +5% over | Low | 0.8–1.2 | Stable | **Trim overweight — Redistribute** |
| Within target | High (>0.7) between holdings | Any | Declining | **Replace correlated stock with uncorrelated** |
| Within target | Low | > 1.5 | Declining | **Add defensive / low-beta stock** |
| Within target | Low | < 0.5 | Low | **Add growth / higher-beta stock** |
| Multiple sectors drifted | Mixed | Any | Declining | **Full rebalance — Realign all sector weights** |
| Within target | Low | 0.8–1.2 | Significantly declining | **Review underperformers — Exit thesis-broken positions** |
| New candidate available | Low vs existing | Improves beta | Improves Sharpe | **Initiate — Fund from trimming overweight sector** |

---

## 7. Exit Rules

| Trigger | Rule |
|---|---|
| Stop-Loss | Exit if price falls 8–10% below buy price, regardless of conviction |
| Thesis Broken | Exit if the original investment reason no longer holds, even if price is up |
| Overvaluation | Consider trimming if PEG > 2.5 and RSI > 70 simultaneously |
| Concentration | Trim if a single stock grows beyond 15–20% of total portfolio value |
| Sector Drift | Rebalance if any sector exceeds target allocation by > 5% |

---

## 8. Computability Assessment

| Category | # Metrics | Automation Level |
|---|---|---|
| Fully computable from data | ~14 | 🤖 Full automation |
| Requires external API data | ~10 | 🔌 API integration needed |
| Requires AI / NLP (news sentiment, earnings tone) | ~3 | 🧠 Claude AI powered |
| Judgement-based (thesis integrity, moat) | ~3 | 👤 Manual user input |

**~85% of the framework is fully automatable.**

---

## 9. Data Sources Required
*Scope: Indian Stock Market (NSE / BSE). All sources are free — no paid API subscriptions.*

### 9.1 Price & Technical Data

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| Stock price & historical data | Yahoo Finance (`TICKER.NS` for NSE, `TICKER.BO` for BSE) | `yfinance` Python library | Most reliable free source; covers full NSE/BSE universe |
| Real-time & intraday price | NSE India (nseindia.com) | Unofficial NSE API / `nsetools` Python library | Unofficial — can be fragile if NSE changes endpoints |
| Index levels (Nifty 50, Sensex) | NSE India, Yahoo Finance | `yfinance` (`^NSEI`, `^BSESN`) | Free and reliable |
| Nifty Sector Indices | NSE India | Unofficial NSE API | Nifty Bank, IT, Pharma, FMCG etc. |
| India VIX | NSE India | Unofficial NSE API / `yfinance` (`^INDIAVIX`) | Free |
| F&O Data (Put/Call Ratio) | NSE India | Unofficial NSE API | Proxy for short interest in Indian context |
| Bulk & Block Deals | NSE India | Unofficial NSE API / BSE India | Free; good proxy for large institutional moves |

### 9.2 Fundamental & Financial Data

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| Revenue, EPS, Net Income, Margins | Yahoo Finance | `yfinance` Python library | Good coverage; some gaps for smaller caps |
| Free Cash Flow, Operating Cash Flow | Yahoo Finance | `yfinance` Python library | Available for most NSE-listed companies |
| Debt-to-Equity, Current Ratio | Yahoo Finance | `yfinance` Python library | Available as summary stats |
| P/E, P/B, P/S Ratios | Yahoo Finance | `yfinance` Python library | Live ratios available |
| EV/EBITDA, PEG Ratio | Screener.in | Web scraping (free tier) | Screener.in has excellent 10-year financial history |
| ROIC, ROE, ROA | Screener.in | Web scraping (free tier) | Computed and displayed on stock pages |
| Quarterly financial history | Screener.in | Web scraping (free tier) | Best free source for multi-year quarterly data |
| Peer / sector comparison | Screener.in | Web scraping (free tier) | Peer group ratios available on each stock page |

### 9.3 Shareholding & Insider Data

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| Promoter Holding % | BSE India filings, Screener.in | BSE API endpoints / scraping | Quarterly filings — mandated by SEBI |
| Promoter Pledge % | BSE India filings, Screener.in | BSE API endpoints / scraping | Critical India-specific risk metric |
| FII / DII / MF Holding | BSE India shareholding filings | BSE API endpoints / scraping | Quarterly; tracks institutional flows |
| Institutional Ownership Change | BSE India filings | BSE API endpoints | Compare quarter-on-quarter |
| Insider buying / selling | NSE / BSE corporate announcements | Unofficial NSE API / BSE filings | SEBI-mandated disclosures |

### 9.4 Analyst & Estimate Data

| Data Type | Free Source | Access Method | Limitation |
|---|---|---|---|
| Analyst EPS estimates | Yahoo Finance | `yfinance` Python library | Available for larger Nifty 500 stocks; limited for small caps |
| Analyst price targets | Yahoo Finance | `yfinance` Python library | Consensus target available for covered stocks |
| Earnings surprise % | Yahoo Finance | `yfinance` (actuals vs estimates) | Can be computed from actuals vs estimates |
| Analyst upgrades / downgrades | Moneycontrol, ET Markets | Web scraping / RSS feeds | ⚠️ No clean free API — manual or scraped |

### 9.5 News & Sentiment Data

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| Financial news headlines | Economic Times RSS, Business Standard RSS, Moneycontrol RSS | RSS feed parsing (free) | No API key needed; standard RSS |
| Company-specific announcements | NSE India, BSE India | Official announcement feeds (free) | Best source for corporate events |
| Broader market news | Google News RSS (filtered by stock name / ticker) | RSS feed parsing (free) | Good for sentiment scanning |
| News sentiment scoring | Claude AI API | Anthropic API | Feed headlines to Claude for NLP scoring |

### 9.6 Macro & Market Indicators

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| RBI Repo Rate | RBI Website (rbi.org.in) | Web scraping / RBI data releases | Free; updated on policy announcement dates |
| CPI Inflation | MOSPI (mospi.gov.in) | Web scraping / data downloads | Monthly releases |
| GDP Growth | MOSPI / World Bank API | World Bank open API (free) | Quarterly |
| GST Collections | GST Council (gst.gov.in) | Web scraping / press releases | Monthly |
| India PMI | Trading Economics (free tier) | Web scraping | Manufacturing & Services PMI |

### 9.7 Stock Screening Universe

| Data Type | Free Source | Access Method | Notes |
|---|---|---|---|
| Nifty 50 / 100 / 500 constituents | NSE India | Unofficial NSE API / CSV download | Full list available free |
| Stock screener (filter by metrics) | Screener.in (free tier) | Web-based screener | Powerful free screener with custom filters |
| Screened stock list export | Screener.in | Manual export or scraping | Free tier allows basic screening |

---

### 9.8 Free Source Limitations to Be Aware Of

| Limitation | Impact | Mitigation |
|---|---|---|
| NSE unofficial API can break when NSE updates its website | Price/F&O data may go down temporarily | Fallback to `yfinance` for price data |
| Screener.in scraping may hit rate limits | Fundamental data refresh may be slow | Cache data locally; refresh weekly not daily |
| Analyst upgrade/downgrade data has no clean free API | This signal will be partially manual | Scrape Moneycontrol/ET Markets RSS for headline signals |
| Small & mid cap stocks have thinner analyst coverage | Estimates and targets may be unavailable | Flag as "insufficient analyst data" in scoring |
| yfinance data can have occasional gaps or delays | Some metrics may be stale | Cross-validate key metrics with Screener.in |
| Free news APIs (NewsAPI free tier: 100 calls/day) | Limits how many stocks can be monitored daily | Prioritise news fetch for portfolio stocks first; watchlist second |

---

## 10. Ongoing Sustainment Requirements

| Cadence | Activity |
|---|---|
| Daily | Full integrated analysis run (G1 → G2 → G3 in one block), stop-loss proximity alerts, news sentiment refresh |
| Weekly | Technical indicator refresh, peer comparison refresh |
| Monthly | Fundamentals refresh, shareholding update, sector allocation review |
| Quarterly | Full portfolio rebalancing review, performance attribution |
| Event-driven | Earnings releases, analyst upgrades/downgrades, major macro announcements |

### Integrated Run Cadence
A single scheduled run triggers all three goals in sequence:
```
Daily at 16:30 IST (after market close):
    Shared data fetch → G1 → G2 → G3 → Alerts → Store results
```

---

## 11. Key Design Principles

- **Fundamentals decide WHAT to own. Technicals decide WHEN to act. Sentiment decides HOW MUCH conviction to have.**
- Sector context always applies — no metric is evaluated in isolation from its sector
- Trend direction matters more than a point-in-time snapshot
- Portfolio-level decisions take precedence over individual stock signals when they conflict
- The system must learn from its own recommendations via performance attribution over time

---

*Document Status: Baselined — Ready for solution architecture and build planning*