"""CFTC Traders in Financial Futures (TFF) report — CME Bitcoin futures positioning.

Uses the `fut_fin_txt_{year}.zip` file which contains Bitcoin CME futures.
Key categories:
  Asset Manager  — long-only institutions, mutual funds, pension funds
  Leveraged Money — hedge funds, CTAs; typically has both long and short sides
"""
import io
import zipfile
from datetime import datetime, timezone

import pandas as pd

from .http import get_bytes

CFTC_BASE = "https://www.cftc.gov/files/dea/history"
MARKET_NAME = "BITCOIN - CHICAGO MERCANTILE EXCHANGE"


def _download_year(year: int) -> pd.DataFrame:
    url = f"{CFTC_BASE}/fut_fin_txt_{year}.zip"
    with zipfile.ZipFile(io.BytesIO(get_bytes(url, timeout=90))) as z:
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        with z.open(csv_name) as f:
            return pd.read_csv(f, low_memory=False)


def _parse_btc_rows(df: pd.DataFrame) -> list[dict]:
    btc = df[df["Market_and_Exchange_Names"].str.strip() == MARKET_NAME].copy()
    rows = []
    for _, row in btc.iterrows():
        # TFF file uses YYYY-MM-DD format in Report_Date_as_YYYY-MM-DD
        try:
            date_str = str(row.get("Report_Date_as_YYYY-MM-DD", "")).strip()
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue

        # TFF column names differ from Disaggregated COT
        am_long  = float(row.get("Asset_Mgr_Positions_Long_All",  0) or 0)
        am_short = float(row.get("Asset_Mgr_Positions_Short_All", 0) or 0)
        lm_long  = float(row.get("Lev_Money_Positions_Long_All",  0) or 0)
        lm_short = float(row.get("Lev_Money_Positions_Short_All", 0) or 0)
        total_oi = float(row.get("Open_Interest_All",             0) or 0)

        am_total = am_long + am_short
        lm_total = lm_long + lm_short

        rows.append({
            "date":       report_date,
            "am_long":    am_long,
            "am_short":   am_short,
            "am_net":     am_long - am_short,
            # When AM is predominantly long-only, am_net_pct approaches 1.0 — use lm as primary signal
            "am_net_pct": (am_long - am_short) / am_total if am_total > 0 else None,
            "lm_long":    lm_long,
            "lm_short":   lm_short,
            "lm_net":     lm_long - lm_short,
            "lm_net_pct": (lm_long - lm_short) / lm_total if lm_total > 0 else None,
            "total_oi":   total_oi,
        })
    return rows


def fetch_cot_snapshot() -> dict:
    """Fetch current year's COT and return the latest weekly observation."""
    year = datetime.now(timezone.utc).year
    df = _download_year(year)
    rows = _parse_btc_rows(df)
    if not rows:
        raise ValueError(f"No Bitcoin CME rows in {year} TFF COT")
    rows.sort(key=lambda r: r["date"])
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latest": rows[-1],
        "all_rows": rows,
    }


def fetch_cot_history(start_year: int = 2018) -> list[dict]:
    """Download all COT history from start_year to present, deduplicated by date."""
    current_year = datetime.now(timezone.utc).year
    all_rows: list[dict] = []
    for year in range(start_year, current_year + 1):
        try:
            df = _download_year(year)
            rows = _parse_btc_rows(df)
            all_rows.extend(rows)
            print(f"  COT {year}: {len(rows)} rows")
        except Exception as exc:
            print(f"  WARN: COT {year} failed: {exc}")

    seen: set = set()
    unique: list[dict] = []
    for r in all_rows:
        if r["date"] not in seen:
            seen.add(r["date"])
            unique.append(r)
    unique.sort(key=lambda r: r["date"])
    return unique
