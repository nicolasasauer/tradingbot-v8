# TradingBot v8 – SmartAlpha on Raspberry Pi

> [!WARNING]
> **🤖 Vibe Coded — AI-Generated Project**
>
> This entire project was generated with the assistance of an AI coding agent.
> That means it *might* work perfectly, it *might* have subtle bugs, or it *might*
> do something completely unexpected with your money. We genuinely don't know yet —
> and neither does the AI.
>
> **Before you run anything, especially with real funds:**
> - 📖 Read every file. Understand what it does.
> - 🔍 Audit `SmartAlphaStrategy.py` — this is the code making trade decisions.
> - 🔐 Review `config.json` — it contains your API keys and risk parameters.
> - 🧪 Always test in **dry-run mode first** (it is on by default, but double-check).
> - 💸 Never risk money you cannot afford to lose.
>
> The authors and the AI take **zero responsibility** for financial losses.
> Crypto trading is inherently risky. AI-generated crypto trading code is *extra* risky.
> You have been warned. Vibe responsibly. ✌️

---

A production-ready **Freqtrade** trading bot configured for **Binance** (via CCXT),
running inside Docker on a Raspberry Pi (ARM64). Starts in **Dry-Run (Paper Trading)**
mode so you can evaluate performance before risking real funds.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start (one command)](#quick-start)
4. [Configuration](#configuration)
5. [Strategy: SmartAlphaStrategy](#strategy-smartalphastrategy)
6. [Self-Improvement (Hyperopt)](#self-improvement-hyperopt)
7. [Web UI (FreqUI)](#web-ui-frequi)
8. [Directory Structure](#directory-structure)
9. [Useful Commands](#useful-commands)

---

## Architecture Overview

```
Raspberry Pi (ARM64)
│
├── Docker Compose
│   └── freqtrade (freqtradeorg/freqtrade:stable)
│       ├── SmartAlphaStrategy  (RSI + EMA + Bollinger Bands)
│       ├── Binance / CCXT      (exchange connector)
│       ├── FreqUI              (Web dashboard on :8080)
│       └── SQLite              (trade database)
│
└── user_data/
    ├── config.json             (bot configuration)
    ├── strategies/             (strategy files)
    ├── data/                   (downloaded market data)
    ├── logs/                   (log files)
    ├── backtest_results/
    └── hyperopt_results/
```

### How It Works

| Component | Role |
|---|---|
| **Freqtrade** | Open-source crypto trading framework handling order lifecycle, risk management, and reporting |
| **SmartAlphaStrategy** | Custom strategy combining RSI (momentum), EMA-20/50/200 (trend), and Bollinger Bands (volatility) |
| **Dry Run mode** | Simulates trades against live market data with a virtual wallet — zero real money at risk |
| **FreqUI** | Real-time web dashboard to monitor open trades, P&L, and performance charts |
| **Hyperopt** | Bayesian parameter search to automatically tune entry/exit thresholds using historical data |

---

## Prerequisites

- Raspberry Pi 4 or 5 (4 GB RAM recommended) running a 64-bit OS (e.g. Raspberry Pi OS Lite 64-bit)
- Docker & Docker Compose v2 installed:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  # Log out and back in for group changes to take effect
  ```
- A free [Binance account](https://www.binance.com) (API keys needed only for live trading; dry-run works without them)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/nicolasasauer/tradingbot-v8.git
cd tradingbot-v8

# 2. (Optional) Edit credentials in user_data/config.json
#    Set api_server.username and api_server.password

# 3. Start everything with one command
docker compose up -d

# 4. Open the Web UI
#    http://<raspberry-pi-ip>:8080
```

The bot will start in **dry-run mode** immediately, trading a virtual wallet of **1000 USDT**.

To follow the logs:

```bash
docker compose logs -f freqtrade
```

To stop the bot:

```bash
docker compose down
```

---

## Configuration

All bot settings live in **`user_data/config.json`**.

| Key | Default | Description |
|---|---|---|
| `dry_run` | `true` | Paper trading — no real orders are placed |
| `dry_run_wallet` | `1000` | Starting virtual balance in USDT |
| `stake_amount` | `200` | Amount in USDT allocated per trade |
| `max_open_trades` | `5` | Maximum simultaneous open positions |
| `exchange.key` | placeholder | Your Binance API key (required for live) |
| `exchange.secret` | placeholder | Your Binance API secret (required for live) |
| `api_server.username` | `freqtrader` | FreqUI login username |
| `api_server.password` | placeholder | **Change this before deploying!** |
| `api_server.jwt_secret_key` | placeholder | **Change this before deploying!** |

> **Security note:** Before deploying, replace all `CHANGE_THIS_*` and `YOUR_*` placeholders
> in `config.json` with real values. Never commit real API keys to version control.

To switch to **live trading**, set `"dry_run": false` and fill in your Binance API credentials.

---

## Strategy: SmartAlphaStrategy

File: `user_data/strategies/SmartAlphaStrategy.py`

### Indicators

| Indicator | Period | Purpose |
|---|---|---|
| **RSI** | 14 | Momentum – identify oversold / overbought conditions |
| **EMA-20** | 20 | Short-term trend direction |
| **EMA-50** | 50 | Medium-term trend direction |
| **EMA-200** | 200 | Long-term macro trend filter |
| **Bollinger Bands** | 20, 2σ | Volatility channel – mean-reversion signals |
| **MACD** | 12/26/9 | Auxiliary momentum confirmation |

### Entry Logic (Long)

All of the following must be true:

1. **RSI < 30** (oversold — price has fallen fast, rebound likely)
2. **EMA-20 > EMA-50** (short-term trend is up)
3. **Close > EMA-200** (macro uptrend filter — avoid bear markets)
4. **Close ≤ Lower Bollinger Band** (price at the statistical low of its recent range)
5. **Volume > 50% of 20-period average** (avoid illiquid candles)

### Exit Logic

Exits trigger on **either** condition:

1. **RSI > 70** (overbought — momentum exhausted)
2. **Close ≥ Upper Bollinger Band** (price at the statistical high)

### Protective Mechanisms

| Mechanism | Value | Description |
|---|---|---|
| Hard stop-loss | −5 % | Absolute maximum loss per trade |
| Trailing stop | activates at +2 % | Follows price up, locks in gains |
| Trailing offset | +3 % | Trailing starts from 3 % profit |
| Dynamic stop | custom | Locks in 2 % / 5 % at profit milestones |

### ROI Table (time-based fallback exits)

| Time (minutes) | Target |
|---|---|
| 0 | 10 % |
| 60 | 5 % |
| 120 | 3 % |
| 240 | 1 % |

---

## Self-Improvement (Hyperopt)

The `optimize.sh` script automates the full optimization workflow:

1. Downloads recent market data from Binance
2. Runs Freqtrade's **hyperopt** to search for the best buy/sell parameter combination
3. Prints the suggested parameters

```bash
# Default: 30 days of data, 100 epochs
bash optimize.sh

# Custom: 60 days of data, 300 epochs
bash optimize.sh --days 60 --epochs 300
```

Results are saved to `user_data/hyperopt_results/`. To view the best run:

```bash
docker compose run --rm freqtrade hyperopt-show --best
```

To apply the best parameters permanently, copy the printed `params` block into
`SmartAlphaStrategy.py` as the default values for the hyperopt parameters.

> **Tip:** Run hyperopt weekly to keep the strategy adapted to current market conditions.

---

## Web UI (FreqUI)

FreqUI is served directly by the Freqtrade API server at **port 8080**.

1. Open your browser and navigate to `http://<raspberry-pi-ip>:8080`
2. Log in with the credentials set in `config.json` → `api_server.username` / `api_server.password`

The dashboard shows:

- Open and closed trades with P&L
- Performance metrics (win rate, profit factor, Sharpe ratio)
- Live pair charts with indicator overlays
- Bot status and log stream

---

## Directory Structure

```
tradingbot-v8/
├── docker-compose.yml               # Service definitions
├── optimize.sh                      # Hyperopt automation script
├── README.md                        # This file
└── user_data/                       # Freqtrade working directory
    ├── config.json                  # Bot & exchange configuration
    ├── strategies/
    │   └── SmartAlphaStrategy.py    # Trading strategy
    ├── data/                        # Downloaded OHLCV candle data
    ├── logs/                        # Bot log files
    ├── backtest_results/            # Backtesting output
    ├── hyperopt_results/            # Hyperopt output
    └── plot/                        # Trade plot images
```

---

## Useful Commands

```bash
# Start the bot in the background
docker compose up -d

# View live logs
docker compose logs -f freqtrade

# Stop the bot
docker compose down

# Run a backtest (last 30 days)
docker compose run --rm freqtrade backtesting \
  --config /freqtrade/user_data/config.json \
  --strategy SmartAlphaStrategy \
  --timerange "$(date -d '30 days ago' +%Y%m%d)-$(date +%Y%m%d)"

# Show open trades
docker compose run --rm freqtrade show-trades \
  --config /freqtrade/user_data/config.json

# Update the Freqtrade image
docker compose pull && docker compose up -d
```