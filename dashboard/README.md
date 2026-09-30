# Gas & LNG Market Dashboard

A Streamlit dashboard for gas and LNG market monitoring.

## Setup (Mac)

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r dashboard/requirements.txt

# 3. (Optional) Set your GIE API key as an env variable
export GIE_API_KEY="your_key_here"

# 4. Run the dashboard
streamlit run dashboard/app.py
```

The dashboard opens automatically in your browser at `http://localhost:8501`.

## Data Sources

| Benchmark | Source | Key required |
|-----------|--------|--------------|
| Henry Hub (NG=F) | yfinance / CME | No |
| TTF (TTF=F) | yfinance / ICE | No (delayed) |
| NBP (BNG=F) | yfinance / ICE | No (delayed) |
| EU Gas Storage | AGSI+ / GIE | **Free** — register at [agsi.gie.eu](https://agsi.gie.eu/) |
| JKM / DES NWE | Platts | Paid subscription — enter manually in sidebar |

## Getting a GIE API Key (free)

1. Go to [agsi.gie.eu](https://agsi.gie.eu/)
2. Click **Register** and create a free account
3. After login, go to your profile → API Key
4. Paste the key into the sidebar, or set `GIE_API_KEY` in your shell

## Storing the key (optional)

Create `dashboard/.streamlit/secrets.toml`:

```toml
GIE_API_KEY = "your_key_here"
```

This avoids having to re-enter it each session.
