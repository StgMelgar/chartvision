#!/bin/bash
# TradingView Chart Vision - Launcher Script
# This script launches the app independently so you can close Terminal

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Run the app with pythonw (no Terminal required) or fall back to python3
if command -v pythonw3 &> /dev/null; then
    nohup pythonw3 chart_vision_app.py > /dev/null 2>&1 &
elif command -v python3 &> /dev/null; then
    nohup python3 chart_vision_app.py > /dev/null 2>&1 &
else
    echo "Python 3 not found. Please install Python 3."
    exit 1
fi

echo "TradingView Chart Vision launched!"
echo "You can close this Terminal window now."
