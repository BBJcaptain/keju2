# UOB Gold Prices Tracker

Automatically fetches UOB gold prices, spot gold prices from multiple sources, and USD/SGD exchange rates every 10 minutes using GitHub Actions.

## Data Sources

This script fetches from **5 reliable sources** with automatic averaging:

1. **UOB Cast 1kg Bar** - https://www.uobgroup.com/wsm/gold-silver
2. **XAUUSD Spot** (TradingView) - https://www.tradingview.com/symbols/XAUUSD/
3. **XAUUSD Spot** (CNBC) - https://www.cnbc.com/quotes/XAU=
4. **USD/SGD** (CNBC) - https://www.cnbc.com/quotes/sgd=x
5. **USD/SGD** (Yahoo Finance) - https://finance.yahoo.com/quote/SGD%3DX/

Prices are **averaged** from multiple sources for accuracy.

## Setup Instructions

1. **Create GitHub repository**
   ```bash
   # Create new repo at https://github.com/new
   # Name: uob-gold-prices
   # Make it PUBLIC (so OpenClaw can access without auth)
   ```

2. **Upload files**
   - Upload `fetch_gold_prices.py` to root
   - Create folder `.github/workflows/`
   - Upload `fetch-gold-prices.yml` to `.github/workflows/`

3. **Enable GitHub Actions**
   - Go to repository Settings > Actions > General
   - Under "Workflow permissions", select "Read and write permissions"
   - Click Save

4. **Trigger first run**
   - Go to Actions tab
   - Click "Fetch Gold Prices" workflow
   - Click "Run workflow" button
   - Wait 30 seconds
   - Check for `gold_prices.json` in repository

## Access the data

The data is available at:
```
https://raw.githubusercontent.com/YOUR_USERNAME/uob-gold-prices/main/gold_prices.json
```

Replace `YOUR_USERNAME` with your GitHub username.

## Data Structure

```json
{
  "last_updated": "2026-02-16T12:00:00Z",
  "uob_prices_sgd": {
    "1kg_cast_buy": 85420.00,
    "1kg_cast_sell": 84820.00
  },
  "gold_spot_usd_per_oz": {
    "average": 2850.50,
    "sources": {
      "tradingview": 2851.20,
      "cnbc": 2849.80
    },
    "source_count": 2,
    "source_names": ["TradingView", "CNBC"]
  },
  "usd_sgd_rate": {
    "average": 1.3245,
    "sources": {
      "cnbc": 1.3243,
      "yahoo": 1.3247
    },
    "source_count": 2,
    "source_names": ["CNBC", "Yahoo"]
  },
  "calculated": {
    "spot_price_sgd_per_gram": 121.45,
    "spot_price_sgd_per_kg": 121450.00,
    "uob_1kg_premium_sgd": 420.00,
    "uob_1kg_premium_percent": 0.35,
    "uob_spread_sgd": 600.00,
    "uob_spread_percent": 0.70
  },
  "status": {
    "uob_success": true,
    "gold_spot_success": true,
    "forex_success": true,
    "all_sources_success": true
  }
}
```

### Key Fields

- **uob_prices_sgd.1kg_cast_buy** - UOB 1kg cast bar buy price (SGD)
- **uob_prices_sgd.1kg_cast_sell** - UOB 1kg cast bar sell price (SGD)
- **gold_spot_usd_per_oz.average** - Average spot price from TradingView & CNBC (USD/oz)
- **usd_sgd_rate.average** - Average USD/SGD from CNBC & Yahoo
- **calculated.spot_price_sgd_per_kg** - Spot price in SGD per kilogram
- **calculated.uob_1kg_premium_sgd** - Premium over spot for UOB 1kg bar
- **calculated.uob_spread_sgd** - Buy/sell spread for UOB bar

## Use with OpenClaw

In your Telegram chat with OpenClaw:

```
What's the current UOB gold price?
```

OpenClaw will fetch from:
```
https://raw.githubusercontent.com/YOUR_USERNAME/uob-gold-prices/main/gold_prices.json
```

## Troubleshooting

**GitHub Actions not running?**
- Check Settings > Actions is enabled
- Check workflow file is in `.github/workflows/` folder
- Check "Read and write permissions" is enabled

**Data not updating?**
- Check Actions tab for failed workflows
- Click on failed workflow to see error logs
- UOB prices may fail if website structure changes

**Need to test immediately?**
- Go to Actions tab
- Click "Fetch Gold Prices"
- Click "Run workflow"

## Update Frequency

- Runs every 10 minutes automatically
- Manual trigger available via GitHub Actions
- Free tier: 2,000 minutes/month (plenty for this use case)

## Notes

- GitHub Actions runners are NOT blocked by UOB (unlike Hetzner VPS)
- Data is publicly accessible (no authentication needed)
- Free to run on public repositories
- Perfect for OpenClaw integration
