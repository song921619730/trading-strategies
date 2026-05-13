#!/bin/bash
# scan_every_minute.sh — Wrapper for system crontab
# Runs the autopilot scanner every minute via Windows Python
WINDOWS_PYTHON="/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe"
SCRIPT="F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/scanner_autopilot.py"

# Set MT5 env vars (from Hermes .env or fallback)
export MT5_PATH="C:/Program Files/MetaTrader 5/terminal64.exe"
export MT5_LOGIN=""
export MT5_PASSWORD=""
export MT5_SERVER=""

# Remove previous minute's trigger to prevent double-read
rm -f /mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/logs/triggers/.latest

"$WINDOWS_PYTHON" "$SCRIPT" >> /mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/logs/scanner_debug.log 2>&1

# Copy latest trigger (if any) for Hermes cron to pick up
LATEST=$(ls -t /mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/logs/triggers/ 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
  cp "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/logs/triggers/$LATEST" \
     "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/logs/triggers/.latest" 2>/dev/null
fi
