"""
Data fetching for the gas/LNG dashboard.

Sources:
  - Henry Hub  : yfinance (NG=F, CME)
  - TTF        : yfinance (TTF=F, ICE delayed)
  - NBP        : yfinance (BNG=F, ICE delayed)
  - EU Storage : AGSI+ / GIE API (free key at agsi.gie.eu)
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGSI_BASE = "https://agsi.gie.eu/api"

PRICE_CONFIGS = {
    "Henry Hub": {"ticker": "NG=F",  "unit": "USD/MMBtu"},
    "TTF":       {"ticker": "TTF=F", "unit": "EUR/MWh"},
    "NBP":       {"ticker": "BNG=F", "unit": "p/therm"},
}


def _gie_key() -> str:
    """Return GIE API key from secrets or environment."""
    try:
        return st.secrets.get("GIE_API_KEY", "")
    except Exception:
        return os.environ.get("GIE_API_KEY", "")


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800)
def fetch_price(name: str) -> dict | None:
    """
    Fetch the latest price for a benchmark from yfinance.
    Returns dict with price, change, pct_change, unit, or None on failure.
    """
    cfg = PRICE_CONFIGS.get(name)
    if not cfg:
        return None
    try:
        hist = yf.Ticker(cfg["ticker"]).history(period="5d", interval="1d")
        if hist.empty:
            return None
        hist = hist.dropna(subset=["Close"])
        if len(hist) < 1:
            return None
        latest = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else latest
        return {
            "price":      latest,
            "change":     latest - prev,
            "pct_change": (latest - prev) / prev * 100 if prev else 0.0,
            "unit":       cfg["unit"],
            "as_of":      hist.index[-1].date(),
        }
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_hh_history(days: int = 365) -> pd.DataFrame | None:
    """Return daily HH closes as a DataFrame with index=date, column='Close'."""
    try:
        hist = yf.Ticker("NG=F").history(period=f"{days}d", interval="1d")
        if hist.empty:
            return None
        hist.index = hist.index.tz_localize(None)
        return hist[["Close"]]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AGSI+ storage data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_agsi_storage(country: str = "eu") -> tuple[pd.DataFrame | None, str | None]:
    """
    Fetch ~5.5 years of AGSI+ storage data for the given country code.
    Returns (df, error_msg). error_msg is None on success, 'no_key' if key missing.

    df columns: date (datetime), gasInStorage (bcm), full (%), trend
    """
    key = _gie_key()
    if not key:
        return None, "no_key"

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=365 * 5 + 200)).strftime("%Y-%m-%d")

    try:
        r = requests.get(
            AGSI_BASE,
            headers={"x-key": key},
            params={"country": country, "from": start, "to": end, "size": 3000},
            timeout=15,
        )
        r.raise_for_status()
        payload = r.json()

        # API may return list directly or wrapped in {"data": [...]}
        records = payload if isinstance(payload, list) else payload.get("data", [])
        if not records:
            return None, "Empty response from AGSI+ API"

        df = pd.DataFrame(records)
        df["date"]         = pd.to_datetime(df["gasDayStartedOn"])
        df["full"]         = pd.to_numeric(df["full"],         errors="coerce")
        df["gasInStorage"] = pd.to_numeric(df["gasInStorage"], errors="coerce")
        df["trend"]        = pd.to_numeric(df.get("trend",     pd.NA), errors="coerce")
        df = df.sort_values("date").dropna(subset=["date", "full"])
        return df, None

    except requests.HTTPError as e:
        return None, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return None, str(e)


def compute_storage_seasonal(df: pd.DataFrame) -> dict:
    """
    Build seasonal storage series mapped onto the current calendar year
    so all lines share the same x-axis for seasonal comparison.

    Returns dict:
      years        : {year: pd.Series(index=mapped_date, values=full%)}
      current_year : int
      avg          : pd.Series (5yr historical average mapped to current year)
      min5y        : pd.Series
      max5y        : pd.Series
    """
    df = df.copy()
    current_year = datetime.today().year

    def _map_date(d: pd.Timestamp, target: int) -> pd.Timestamp:
        try:
            return d.replace(year=target)
        except ValueError:
            return d.replace(year=target, day=28)  # Feb 29 in non-leap year

    years_present = sorted(df["date"].dt.year.unique())
    series_by_year = {}
    for yr in years_present:
        sub = df[df["date"].dt.year == yr].copy()
        sub["mapped"] = sub["date"].apply(lambda d: _map_date(d, current_year))
        series_by_year[yr] = sub.set_index("mapped")["full"].sort_index()

    # 5yr historical range and average (exclude current year)
    hist_years = [yr for yr in years_present if yr < current_year][-5:]
    if hist_years:
        combined = pd.DataFrame({yr: series_by_year[yr] for yr in hist_years})
        avg   = combined.mean(axis=1)
        min5y = combined.min(axis=1)
        max5y = combined.max(axis=1)
    else:
        avg = min5y = max5y = None

    return {
        "years":        series_by_year,
        "current_year": current_year,
        "avg":          avg,
        "min5y":        min5y,
        "max5y":        max5y,
    }
