Suggested Priority Areas to Explore Next
Before you decide, here are the areas most likely to improve the core:

1. Data Quality: 
    a) Screener.in scraping for deeper fundamentals (ROIC, EV/EBITDA from peers)
    b) Better earnings estimate data for surprise % calculation

2. Scoring Accuracy: 
    a) Sector-relative thresholds (a 4% margin is green for retail, red for software) 
    c) Backtesting — did past recommendations actually work?

3. Dashboard UX: 
    a) Price chart with MA overlays in stock detail view 
    b) Portfolio performance over time chart

4. Robustness: Error handling improvements and Handling stocks with thin data coverage

****************************************************************************************************************************************

Robustness Gaps to be addressed - 

1. Silent Data Failures
The Problem: When yfinance returns empty or partial data, the system silently falls back to None or amber signals — you can't tell whether a score reflects real data or a data gap.
Example: ROIC shows red — is it because ROIC is genuinely poor, or because the balance sheet data was missing?
Solution: Add a data quality flag per stock — track which metrics had real data vs defaulted to None. Surface this in the dashboard as a data confidence indicator.
TCS.NS — Data Quality: 18/22 metrics ✅ | 4 metrics N/A ⚠️

2. yfinance Rate Limiting and Timeouts
The Problem: When processing multiple stocks, yfinance occasionally times out or returns stale data silently. The current retry logic only applies to Claude API — not yfinance.
Solution: Add a retry wrapper with exponential backoff for all yfinance calls — same pattern we used for Claude AI. Add a configurable timeout parameter.

3. No Validation of Computed Scores
The Problem: If a bug produces a score of 150 or -20, it flows through to the recommendation without any sanity check. A bad input (e.g. corrupted price data) can produce nonsense scores silently.
Solution: Add score boundary validation in scorecard_aggregator.py — clamp all scores to 0–100 and log a warning if clamping was needed.

4. Portfolio DB Concurrent Write Conflicts
The Problem: When the G1 workflow processes multiple stocks, each write to portfolio.db is a separate connection. Under any parallel execution this could cause SQLite lock errors.
Solution: Use a single persistent DB connection per workflow run rather than opening/closing per write. Wrap all writes in a single transaction that commits at the end of the run.

5. Stale Cache Served Without Warning
The Problem: When an external source fails (yfinance down, NSE API broken), the system silently serves stale cached data. You can't tell from the dashboard that the data is 3 days old.
Solution: Add a data freshness indicator in the dashboard — show the cache age for key data points next to each stock.

6. No Input Validation on Excel Import
The Problem: If your Excel file has a ticker that doesn't exist on NSE (e.g. a typo), the system will fail silently during analysis with a cryptic yfinance error rather than catching it at import time.
Solution: Add a ticker validation step in import_portfolio_from_excel() — verify each ticker against yfinance before writing to the DB. Flag invalid tickers immediately at import.

7. Unhandled Edge Cases in Technical Indicators
The Problem: Stocks with less than 200 days of price history (new listings, recently listed companies) will have None for SMA200 and Beta. This is handled but not clearly communicated.
Solution: Add a minimum data requirement check at the start of each technical computation — return a structured insufficient_data signal rather than None, so the dashboard can show "Insufficient history" instead of a blank.

8. No Recovery From Mid-Run Failures
The Problem: If the G1 workflow fails halfway through (e.g. network drops after 10 stocks), results for the first 10 stocks are written to DB but the run is marked as failed. The next run starts from scratch.
Solution: Add checkpoint recovery — track which tickers have been processed in the current run. On restart, skip already-processed tickers and continue from where it left off.

Priority Order
Priority | Fix | Effort | Impact
🔴 High | Score boundary validation | Low | Prevents nonsense recommendations
🔴 High | Ticker validation at import | Low | Catches bad data early
🔴 High | yfinance retry wrapper | Medium | Prevents silent data failures
🟠 Medium | Data quality flag per stock | Medium | Transparency in dashboard
🟠 Medium | Data freshness indicator | Low | Visibility of stale data
🟠 Medium | Single DB transaction per run | Medium | Prevents write conflicts
🟡 Low | Minimum data requirement check | Low | Better UX for thin data stocks
🟡 Low | Checkpoint recovery | High | Resilience for large portfolios