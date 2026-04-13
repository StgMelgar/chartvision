# TradingView Chart Vision

AI-powered chart analysis app that captures your TradingView screen and uses Claude's vision to read prices, detect patterns, generate trading signals, and send alerts.

## Setup

### 1. Install Python 3.8+
Download from [python.org](https://www.python.org/downloads/) if you don't have it.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Get an Anthropic API key
- Go to [console.anthropic.com](https://console.anthropic.com)
- Create an account and generate an API key
- You'll enter this key in the app

### 4. Run the app
```bash
python chart_vision_app.py
```

## How to Use

1. **Enter your API key** in the field at the top of the app
2. **Open TradingView** in your browser or desktop app
3. **Click "Select Region"** — a transparent overlay appears. Click and drag to select the area of your screen showing the chart
4. **Click "Start Monitoring"** to begin automatic analysis at your set interval (default: every 10 seconds)
5. **Or click "Analyze Once"** for a single snapshot analysis

### Tips
- **Context field**: Add info like "AAPL 1H chart" to help the AI be more accurate
- **Interval**: 10-15 seconds is a good balance between freshness and API cost
- **Alerts**: You'll get desktop notifications for strong signals, RSI extremes, and detected patterns
- **Export**: Click "Export Log" to save all analyses to CSV or Excel

## Cost
Each analysis sends one screenshot to Claude's API. Approximate cost: $0.01-0.03 per analysis depending on image size.

At 10-second intervals, running for 1 hour = ~360 analyses = ~$3.60-$10.80/hour.

## Files
- `chart_vision_app.py` — Main GUI application
- `screen_capture.py` — Screen capture logic
- `chart_analyzer.py` — Claude API vision analysis
- `alert_system.py` — Desktop notification system
- `config.json` — Your saved settings
- `requirements.txt` — Python dependencies

## Disclaimer
This tool is for informational and educational purposes only. It does not constitute financial advice. Always do your own research before making trading decisions.
