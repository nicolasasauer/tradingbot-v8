#!/usr/bin/env bash
# optimize.sh – Run Freqtrade hyperopt inside Docker to tune SmartAlphaStrategy
# Usage: bash optimize.sh [--days 30] [--epochs 100]
# Requires: docker-compose.yml in the same directory

set -euo pipefail

# --------------------------------------------------------------------------
# Default configuration
# --------------------------------------------------------------------------
DAYS=${DAYS:-30}         # Number of historical days to download
EPOCHS=${EPOCHS:-100}    # Number of hyperopt epochs
TIMEFRAME=${TIMEFRAME:-1h}
STRATEGY=${STRATEGY:-SmartAlphaStrategy}
PAIRS=${PAIRS:-"BTC/USDT ETH/USDT BNB/USDT SOL/USDT ADA/USDT"}

# Parse optional flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)    DAYS="$2";   shift 2 ;;
    --epochs)  EPOCHS="$2"; shift 2 ;;
    *)         echo "Unknown argument: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "  SmartAlpha Hyperopt Optimizer"
echo "  Strategy  : $STRATEGY"
echo "  Timeframe : $TIMEFRAME"
echo "  Days      : $DAYS"
echo "  Epochs    : $EPOCHS"
echo "========================================================"

# --------------------------------------------------------------------------
# Step 1: Download recent market data
# --------------------------------------------------------------------------
echo ""
echo "[1/3] Downloading market data for the last ${DAYS} days..."
docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/config.json \
  --timeframe "$TIMEFRAME" \
  --days "$DAYS" \
  --pairs $PAIRS

echo "[1/3] Data download complete."

# --------------------------------------------------------------------------
# Step 2: Run hyperopt
# --------------------------------------------------------------------------
echo ""
echo "[2/3] Running hyperopt with ${EPOCHS} epochs – this may take a while..."
docker compose run --rm freqtrade hyperopt \
  --config /freqtrade/user_data/config.json \
  --strategy "$STRATEGY" \
  --hyperopt-loss SharpeHyperOptLoss \
  --spaces buy sell \
  --timeframe "$TIMEFRAME" \
  --timerange "$(date -d "${DAYS} days ago" +%Y%m%d)-$(date +%Y%m%d)" \
  --epochs "$EPOCHS" \
  --jobs -1

echo "[2/3] Hyperopt complete."

# --------------------------------------------------------------------------
# Step 3: Show results
# --------------------------------------------------------------------------
echo ""
echo "[3/3] Best hyperopt results:"
docker compose run --rm freqtrade hyperopt-show \
  --config /freqtrade/user_data/config.json \
  --best \
  --no-header \
  2>/dev/null || echo "  (Run hyperopt first to see results)"

echo ""
echo "========================================================"
echo "  Optimization finished!"
echo "  Results saved to: user_data/hyperopt_results/"
echo ""
echo "  To apply the best parameters, copy the printed"
echo "  'params' block into your strategy file or run:"
echo "    docker compose run --rm freqtrade hyperopt-show --best"
echo "========================================================"
