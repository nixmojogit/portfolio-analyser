"""
report_generator.py
Layer      : Presentation
Owns       : SKILL-P06
Description: Generates formatted PDF portfolio reports using fpdf2.
             Reports saved to data/exports/ with date-stamped filenames.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime


EXPORT_PATH = Path("data/exports")


def generate_pdf_report(
    portfolio_results: dict,
    ranked_candidates: list[dict],
    rebalancing_plan: list[dict],
    config: dict | None = None,
) -> str:
    """
    SKILL-P06: Generate PDF Portfolio Report.
    Produces a structured PDF report with the following sections:
      1. Executive Summary — portfolio value, benchmark comparison, top alerts
      2. Individual Stock Pages — score, recommendation, key metrics per holding
      3. New Opportunities — top 5 G2 candidates summary
      4. Rebalancing Plan — G3 actions table
      5. Appendix — metric definitions and threshold reference
    Saves to: data/exports/portfolio_report_{YYYY-MM-DD}.pdf
    Args:
        portfolio_results  : dict of ticker -> full result dict
        ranked_candidates  : list from SKILL-A04
        rebalancing_plan   : list from SKILL-A06
        config             : merged config dict
    Returns: str — file path of generated PDF
    """
    pass


def _render_executive_summary(pdf, portfolio_results: dict, config: dict) -> None:
    """
    Utility: Render the executive summary page of the PDF report.
    Args:
        pdf              : fpdf2 FPDF instance
        portfolio_results: dict of all holding results
        config           : merged config dict
    """
    pass


def _render_stock_page(pdf, ticker: str, stock_data: dict) -> None:
    """
    Utility: Render a single stock detail page in the PDF report.
    Args:
        pdf        : fpdf2 FPDF instance
        ticker     : stock ticker
        stock_data : full result dict for this ticker
    """
    pass


def _render_rebalancing_table(pdf, rebalancing_plan: list[dict]) -> None:
    """
    Utility: Render the G3 rebalancing plan as a formatted table in the PDF.
    Args:
        pdf              : fpdf2 FPDF instance
        rebalancing_plan : list of action dicts
    """
    pass
