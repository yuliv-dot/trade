"""
Gas & LNG Market Dashboard — Streamlit app.

Run:  streamlit run dashboard/app.py
"""

import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fetchers import (
    compute_storage_seasonal,
    fetch_agsi_storage,
    fetch_hh_history,
    fetch_price,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Gas & LNG Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")

    # GIE API key
    with st.expander("AGSI+ Storage Data", expanded=True):
        st.markdown(
            "European storage requires a **free** GIE API key.  \n"
            "[Register at agsi.gie.eu →](https://agsi.gie.eu/)"
        )
        gie_key = st.text_input(
            "GIE API Key",
            type="password",
            value=os.environ.get("GIE_API_KEY", ""),
            placeholder="paste key here…",
        )
        if gie_key:
            os.environ["GIE_API_KEY"] = gie_key

    # Storage region
    COUNTRY_LABELS = {
        "eu": "Europe (total)",
        "de": "Germany",
        "fr": "France",
        "gb": "United Kingdom",
        "it": "Italy",
        "nl": "Netherlands",
        "at": "Austria",
        "be": "Belgium",
        "es": "Spain",
        "pl": "Poland",
    }
    storage_country = st.selectbox(
        "Storage region",
        options=list(COUNTRY_LABELS.keys()),
        format_func=lambda x: COUNTRY_LABELS[x],
    )

    # Manual LNG prices (Platts/ICIS subscription required for live data)
    st.markdown("---")
    with st.expander("LNG prices (manual override)", expanded=False):
        st.markdown(
            "JKM and DES NWE are Platts/ICIS proprietary.  \n"
            "Enter values from your terminal or subscription."
        )
        jkm_price  = st.number_input("JKM ($/MMBtu)",   min_value=0.0, value=0.0, step=0.1, format="%.2f")
        jkm_chg    = st.number_input("JKM Δ vs prev",   min_value=-20.0, max_value=20.0, value=0.0, step=0.01, format="%.3f")
        desnwe     = st.number_input("DES NWE ($/MMBtu)", min_value=0.0, value=0.0, step=0.1, format="%.2f")
        desnwe_chg = st.number_input("DES NWE Δ vs prev", min_value=-20.0, max_value=20.0, value=0.0, step=0.01, format="%.3f")

    st.markdown("---")
    if st.button("🔄 Refresh all data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Prices auto-refresh every 30 min; storage every 60 min.")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("## 📊 Gas & LNG Market Dashboard")
st.caption(f"Last loaded: {datetime.utcnow().strftime('%d %b %Y  %H:%M UTC')}")
st.divider()

# ---------------------------------------------------------------------------
# Price cards
# ---------------------------------------------------------------------------

st.markdown("#### Benchmark Prices")

def _render_metric(col, label: str, data: dict | None, *, manual_price: float = 0.0, manual_chg: float = 0.0):
    with col:
        if data is not None:
            price_fmt = f"{data['price']:.3f}" if data["unit"] == "p/therm" else f"{data['price']:.2f}"
            delta_str = f"{data['change']:+.3f} ({data['pct_change']:+.1f}%)"
            st.metric(
                label=f"{label} — {data['unit']}",
                value=price_fmt,
                delta=delta_str,
                help=f"As of {data['as_of']}. Source: yfinance.",
            )
        elif manual_price > 0:
            pct = manual_chg / (manual_price - manual_chg) * 100 if (manual_price - manual_chg) else 0
            st.metric(
                label=f"{label} — $/MMBtu",
                value=f"{manual_price:.2f}",
                delta=f"{manual_chg:+.3f} ({pct:+.1f}%)",
                help="Manual entry — no free real-time source for this benchmark.",
            )
        else:
            st.metric(
                label=label,
                value="N/A",
                help="No free real-time data available. Use the manual override in the sidebar.",
            )


# Fetch the three free benchmarks in parallel (Streamlit caches them)
hh_data  = fetch_price("Henry Hub")
ttf_data = fetch_price("TTF")
nbp_data = fetch_price("NBP")

c1, c2, c3, c4, c5 = st.columns(5)
_render_metric(c1, "Henry Hub",  hh_data)
_render_metric(c2, "TTF",        ttf_data)
_render_metric(c3, "NBP",        nbp_data)
_render_metric(c4, "JKM",        None, manual_price=jkm_price,  manual_chg=jkm_chg)
_render_metric(c5, "DES NWE",    None, manual_price=desnwe,      manual_chg=desnwe_chg)

st.divider()

# ---------------------------------------------------------------------------
# European gas storage
# ---------------------------------------------------------------------------

st.markdown("#### European Gas Storage (AGSI+)")

storage_df, storage_err = fetch_agsi_storage(storage_country)

if storage_err == "no_key":
    st.info(
        "Enter your free **GIE API key** in the sidebar to display EU storage data.  \n"
        "Registration is free: [agsi.gie.eu](https://agsi.gie.eu/)"
    )

elif storage_err:
    st.warning(f"Could not load storage data: `{storage_err}`")

else:
    seasonal = compute_storage_seasonal(storage_df)

    fig = go.Figure()

    # 5yr range shading
    if seasonal["min5y"] is not None:
        x_shared = seasonal["max5y"].index
        fig.add_trace(go.Scatter(
            x=x_shared, y=seasonal["max5y"].values,
            name="5yr Max", line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=x_shared, y=seasonal["min5y"].values,
            name="5yr Range",
            fill="tonexty", fillcolor="rgba(120,120,200,0.15)",
            line=dict(width=0), hovertemplate="%{y:.1f}%",
        ))
        fig.add_trace(go.Scatter(
            x=seasonal["avg"].index, y=seasonal["avg"].values,
            name="5yr Avg",
            line=dict(color="rgba(180,180,200,0.8)", dash="dash", width=1.5),
            hovertemplate="%{y:.1f}%",
        ))

    # Previous year
    prev_yr = seasonal["current_year"] - 1
    if prev_yr in seasonal["years"]:
        s = seasonal["years"][prev_yr]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            name=str(prev_yr),
            line=dict(color="rgba(255,165,0,0.85)", width=1.8),
            hovertemplate=f"{prev_yr}: %{{y:.1f}}%",
        ))

    # Current year
    cur_yr = seasonal["current_year"]
    if cur_yr in seasonal["years"]:
        s = seasonal["years"][cur_yr]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            name=str(cur_yr),
            line=dict(color="#00d4ff", width=2.5),
            hovertemplate=f"{cur_yr}: %{{y:.1f}}%",
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            title="Storage fill (%)",
            range=[0, 105],
            ticksuffix="%",
            gridcolor="rgba(100,100,100,0.2)",
        ),
        xaxis=dict(
            tickformat="%b",
            dtick="M1",
            gridcolor="rgba(100,100,100,0.2)",
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Stats row
    latest = storage_df.sort_values("date").iloc[-1]
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Date",                    latest["date"].strftime("%d %b %Y"))
    s2.metric("Storage fill",            f"{latest['full']:.1f}%")
    s3.metric("Gas in storage (bcm)",    f"{latest['gasInStorage']:.1f}")
    if pd.notna(latest.get("trend")):
        s4.metric("Daily trend",         f"{latest['trend']:+.2f} pp")
    else:
        s4.metric("Daily trend",         "N/A")

st.divider()

# ---------------------------------------------------------------------------
# Henry Hub price history
# ---------------------------------------------------------------------------

st.markdown("#### Henry Hub — 12-Month Price History")

hh_hist = fetch_hh_history(365)

if hh_hist is not None and not hh_hist.empty:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=hh_hist.index,
        y=hh_hist["Close"],
        name="Henry Hub",
        line=dict(color="#3b82f6", width=2),
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.08)",
        hovertemplate="%{x|%d %b %Y}: $%{y:.3f}/MMBtu",
    ))
    fig2.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            title="USD/MMBtu",
            gridcolor="rgba(100,100,100,0.2)",
        ),
        xaxis=dict(gridcolor="rgba(100,100,100,0.2)"),
        hovermode="x unified",
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Henry Hub history unavailable — check yfinance connectivity.")

# ---------------------------------------------------------------------------
# LNG spreads (requires manual prices above)
# ---------------------------------------------------------------------------

if jkm_price > 0 and hh_data:
    st.divider()
    st.markdown("#### LNG Spreads")

    hh_val   = hh_data["price"]
    jkm_ttf  = jkm_price  - (ttf_data["price"] * 0.293 if ttf_data else 0)  # EUR/MWh → $/MMBtu approx
    atl_arb  = jkm_price  - hh_val   # simplistic net-back: JKM - HH (liquefaction + shipping costs ~$4-6/MMBtu)
    pac_arb  = desnwe     - hh_val   if desnwe > 0 else None

    sa, sb, sc = st.columns(3)
    sa.metric("JKM – HH (gross, $/MMBtu)",  f"{atl_arb:+.2f}", help="Gross margin before liquefaction (~$2.5) + shipping (~$1.5–3)")
    if pac_arb is not None:
        sb.metric("DES NWE – HH (gross, $/MMBtu)", f"{pac_arb:+.2f}")
    if ttf_data:
        ttf_usd = ttf_data["price"] * 0.293  # approximate EUR/MWh → $/MMBtu
        sc.metric("JKM – TTF ($/MMBtu equiv.)", f"{jkm_price - ttf_usd:+.2f}", help="TTF converted at ~0.293 $/MMBtu per EUR/MWh")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "**Data sources** — Henry Hub: CME via yfinance (NG=F, ~15 min delay). "
    "TTF: ICE via yfinance (TTF=F, delayed). "
    "NBP: ICE via yfinance (BNG=F, delayed). "
    "EU Storage: AGSI+ / GIE (daily). "
    "JKM / DES NWE: Platts proprietary — manual entry only."
)
