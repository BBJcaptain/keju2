#!/usr/bin/env python3
"""
Fetch UOB gold prices, spot gold price, and USD/SGD exchange rate
Runs every 15 minutes via GitHub Actions

Sources:
1. UOB gold bar prices (JSON API)
   https://www.uobgroup.com/wsm/gold-silver
2. Gold spot XAUUSD - Source A: CNBC (web scraping)
3. Gold spot XAUUSD - Source B: GoldPrice.org (OTC, with GC=F fallback)
4. USD/SGD + multi-currency forex - Source A: ExchangeRate-API (JSON API)
5. USD/SGD forex - Source B: Frankfurter (JSON API, ECB data)
6. Technical indicators (24H OHLR, Bollinger, MAs, EMAs, ROC, TIMID) — computed from CSV history
7. Correlated assets (Silver, VIX, DXY, SPX, Oil, BTC, Platinum) — yfinance
8. US Treasury yields (3M, 10Y, 30Y) — yfinance
9. CFTC Disaggregated COT for COMEX Gold — weekly, cached between releases
"""

import csv
import io
import json
import os
import re
import requests
import statistics
import sys
import zipfile
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

NO_DATA = 'No Data'

# COMEX market hours: Mon 23:00 UTC - Fri 22:00 UTC (approximate)
# Outside these hours CNBC and GC=F serve stale cached prices.
# XAUUSD=X is an OTC forex pair that continues updating on weekends.
STALE_CONSEC_RUNS = 2  # flag stale after this many unchanged consecutive runs

# Currencies for multi-currency gold pricing (per troy oz in local currency)
GOLD_CURRENCIES = ['EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'INR', 'HKD', 'SGD']

# CFTC COMEX Gold 100 Troy Oz market code
CFTC_GOLD_CODE = '088691'


# =============================================================================
# UOB GOLD PRICES
# =============================================================================

def fetch_uob_prices():
    """Fetch UOB cast 1kg, 100g, and GSA gold prices from the JSON API."""
    errors = []

    try:
        url = "https://www.uobgroup.com/wsm/gold-silver"
        headers = {**HEADERS, 'Referer': 'https://www.uobgroup.com/online-rates/gold-and-silver-prices.page'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        argor_data = None
        cast_data = None
        gsa_data = None

        for item in data.get('types', []):
            description = str(item.get('description', '')).upper()
            unit = str(item.get('unit', '')).upper()

            try:
                buy_price = float(item.get('bankBuy', 0))
                sell_price = float(item.get('bankSell', 0))

                if description == 'ACB' and '100 GM' in unit:
                    argor_data = {
                        'buy': buy_price,
                        'sell': sell_price,
                        'description': 'Argor 100g Cast Bar'
                    }
                    print(f"  Found: Argor 100g - Buy {buy_price}, Sell {sell_price}")

                elif description == 'CTB' and '1 KILOBAR' in unit:
                    cast_data = {
                        'buy': buy_price,
                        'sell': sell_price,
                        'description': 'Cast 1kg Bar'
                    }
                    print(f"  Found: Cast 1kg - Buy {buy_price}, Sell {sell_price}")

                elif 'GSA' in description and buy_price > 0 and sell_price > 0:
                    gsa_data = {
                        'buy': buy_price,
                        'sell': sell_price,
                    }
                    print(f"  Found: GSA - Buy {buy_price}, Sell {sell_price} SGD/gram")

            except (ValueError, TypeError) as e:
                print(f"  Price parsing error for item: {e}")
                continue

        if argor_data and cast_data:
            return {
                'success': True,
                'prices': {
                    '100g_cast_buy': argor_data['buy'],
                    '100g_cast_sell': argor_data['sell'],
                    '1kg_cast_buy': cast_data['buy'],
                    '1kg_cast_sell': cast_data['sell'],
                    'gsa_buy': gsa_data['buy'] if gsa_data else None,
                    'gsa_sell': gsa_data['sell'] if gsa_data else None,
                },
                'source': 'UOB (API)'
            }
        else:
            errors.append(f"Missing data - Argor found: {argor_data is not None}, Cast found: {cast_data is not None}")

    except requests.exceptions.RequestException as e:
        errors.append(f"Network error: {e}")
    except json.JSONDecodeError as e:
        errors.append(f"JSON parsing error: {e}")
    except Exception as e:
        errors.append(f"Unexpected error: {e}")

    return {
        'success': False,
        'error': ' | '.join(errors),
        'prices': {}
    }


# =============================================================================
# GOLD SPOT PRICE (XAUUSD) - 2 SOURCES
# =============================================================================

def fetch_cnbc_gold():
    """Gold spot source A: CNBC web scraping"""
    try:
        url = "https://www.cnbc.com/quotes/XAU="
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        price = None

        price_elem = soup.find('span', {'class': 'QuoteStrip-lastPrice'})
        if price_elem:
            try:
                price = float(re.sub(r'[^\d.]', '', price_elem.get_text().strip()))
            except:
                pass

        if not price:
            for elem in soup.find_all('span', {'class': True}):
                classes = ' '.join(elem.get('class', [])).lower()
                if 'last' in classes and 'price' in classes:
                    try:
                        test_price = float(re.sub(r'[^\d.]', '', elem.get_text().strip()))
                        if 1000 < test_price < 10000:
                            price = test_price
                            break
                    except:
                        pass

        if not price:
            meta = soup.find('meta', {'property': 'og:description'})
            if meta:
                match = re.search(r'\$?([\d,]+\.?\d*)', meta.get('content', ''))
                if match:
                    try:
                        test_price = float(match.group(1).replace(',', ''))
                        if 1000 < test_price < 10000:
                            price = test_price
                    except:
                        pass

        if price and 1000 < price < 10000:
            return {'success': True, 'price': price, 'source': 'CNBC'}

        return {'success': False, 'error': f'Price not found or out of range: {price}', 'price': 0}

    except Exception as e:
        return {'success': False, 'error': str(e), 'price': 0}


def fetch_goldprice_org():
    """Gold spot source B: GoldPrice.org data API, falling back to yfinance GC=F.

    GoldPrice.org aggregates interbank OTC feeds and continues updating outside
    COMEX hours, giving better weekend coverage than exchange-based sources.
    GC=F (COMEX futures) is used as a fallback if the API is unreachable.
    """
    # Primary: GoldPrice.org widget data API
    try:
        url = "https://data-asg.goldprice.org/dbXRates/USD"
        headers = {**HEADERS, 'Origin': 'https://goldprice.org', 'Referer': 'https://goldprice.org/'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        for item in data.get('items', []):
            if item.get('curr') == 'USD':
                price = float(item['xauPrice'])
                if 1000 < price < 10000:
                    return {'success': True, 'price': price, 'source': 'GoldPrice.org'}

    except Exception as e:
        print(f"  GoldPrice.org failed ({e}), trying GC=F fallback...")

    # Fallback: yfinance GC=F COMEX futures
    try:
        import yfinance as yf
        ticker = yf.Ticker("GC=F")
        price = ticker.fast_info.last_price
        if price and 1000 < float(price) < 10000:
            return {'success': True, 'price': float(price), 'source': 'Yahoo Finance (GC=F)'}
        return {'success': False, 'error': f'GC=F price out of range or missing: {price}', 'price': 0}

    except Exception as e:
        return {'success': False, 'error': str(e), 'price': 0}


# =============================================================================
# USD/SGD FOREX - 2 SOURCES
# =============================================================================

def fetch_exchangerate_api_usdsgd():
    """Forex source A: ExchangeRate-API (free, no key).

    Returns SGD rate for backward compatibility plus all currency rates so the
    caller can compute gold prices in multiple currencies without a second request.
    """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('result') == 'success':
            rate = float(data['rates']['SGD'])
            if 1.0 < rate < 2.0:
                return {
                    'success': True,
                    'rate': rate,
                    'rates': data['rates'],
                    'source': 'ExchangeRate-API'
                }

        return {'success': False, 'error': 'Rate not found or out of range', 'rate': 0}

    except Exception as e:
        return {'success': False, 'error': str(e), 'rate': 0}


def fetch_frankfurter_usdsgd():
    """Forex source B: Frankfurter API (free, no key, ECB data)"""
    try:
        url = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=SGD"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        rate = float(data.get('rates', {}).get('SGD', 0))

        if 1.0 < rate < 2.0:
            return {'success': True, 'rate': rate, 'source': 'Frankfurter'}

        return {'success': False, 'error': f'Rate out of range or missing: {rate}', 'rate': 0}

    except Exception as e:
        return {'success': False, 'error': str(e), 'rate': 0}


# =============================================================================
# STALENESS DETECTION
# =============================================================================

def detect_spot_stale(csv_file, current_avg):
    """Return True if gold_spot_usd_avg has been unchanged for STALE_CONSEC_RUNS+ rows.

    Reads the tail of the existing CSV and compares the last N values of
    gold_spot_usd_avg to the current value. A frozen value across multiple
    consecutive scraper runs (outside market hours) indicates a stale cached price.
    """
    if current_avg is None:
        return False
    try:
        if not os.path.exists(csv_file):
            return False
        with open(csv_file, 'r', newline='') as f:
            rows = list(csv.DictReader(f))
        if len(rows) < STALE_CONSEC_RUNS:
            return False
        tail = rows[-STALE_CONSEC_RUNS:]
        return all(
            r.get('gold_spot_usd_avg') and abs(float(r['gold_spot_usd_avg']) - current_avg) < 0.01
            for r in tail
        )
    except Exception:
        return False


def get_csv_fieldnames(csv_file):
    """Return fieldnames from existing CSV header, or None if file doesn't exist."""
    if not os.path.exists(csv_file):
        return None
    try:
        with open(csv_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames) if reader.fieldnames else None
    except Exception:
        return None


# =============================================================================
# TECHNICAL INDICATORS (computed from CSV history, no external API)
# =============================================================================

def _load_price_history(annual_csv_file):
    """Load (timestamp, spot, uob_1kg_sell, uob_gsa_sell) tuples from CSV history.

    Reads the current year's annual CSV and, if present, the prior year's file
    so that long-period indicators (EMA100, ROC63) have enough history at year start.
    """
    spot_series = []
    uob_series  = []
    gsa_series  = []

    try:
        year = int(os.path.basename(annual_csv_file).replace('.csv', ''))
    except ValueError:
        year = datetime.now(timezone.utc).year

    for csv_path in [f'data/{year - 1}.csv', annual_csv_file]:
        if not os.path.exists(csv_path):
            continue
        try:
            with open(csv_path, 'r', newline='') as f:
                for row in csv.DictReader(f):
                    try:
                        ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                        spot_raw = row.get('gold_spot_usd_avg', '').strip()
                        if not spot_raw:
                            continue
                        spot = float(spot_raw)
                        if not (1000 < spot < 10000):
                            continue
                        spot_series.append((ts, spot))
                        uob_raw = row.get('uob_1kg_sell', '').strip()
                        gsa_raw = row.get('uob_gsa_sell', '').strip()
                        uob_series.append((ts, float(uob_raw) if uob_raw else None))
                        gsa_series.append((ts, float(gsa_raw) if gsa_raw else None))
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"  Could not read {csv_path}: {e}")

    return spot_series, uob_series, gsa_series


def compute_technical_indicators(annual_csv_file):
    """Compute 24H OHLR, Bollinger bands, moving averages, EMA oscillator, ROC, and TIMID Score.

    All indicators derive from gold_spot_usd_avg in the existing annual CSV.
    Period units are raw CSV rows (~15-minute intervals each).

    TIMID = Trend Identification & Momentum Indicator Derivative (Weldon, 2007, ch.34).
    Five binary components scored 0/1; sum gives 0-5. Zone: 0-1 NO_TREND,
    2 EMERGING, 3-4 DOMINANT, 5 EXTENDED. Score 5 is a warning to reduce, not add.
    """
    result = {}
    spot_series, uob_series, gsa_series = _load_price_history(annual_csv_file)

    if len(spot_series) < 2:
        print("  Not enough history for technical indicators")
        return result

    now        = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d  = now - timedelta(days=7)

    # ---- 24H OHLR ----
    def _24h_ohlr(series, prefix):
        window = [(ts, v) for ts, v in series if v is not None and ts >= cutoff_24h]
        if not window:
            return {f'{prefix}_24h_open': '', f'{prefix}_24h_high': '',
                    f'{prefix}_24h_low':  '', f'{prefix}_24h_range': ''}
        vals = [v for _, v in window]
        h, l = max(vals), min(vals)
        return {
            f'{prefix}_24h_open':  round(window[0][1], 2),
            f'{prefix}_24h_high':  round(h, 2),
            f'{prefix}_24h_low':   round(l, 2),
            f'{prefix}_24h_range': round(h - l, 2),
        }

    result.update(_24h_ohlr(spot_series, 'spot'))
    result.update(_24h_ohlr(uob_series,  'uob_1kg'))
    result.update(_24h_ohlr(gsa_series,  'uob_gsa'))

    spot_vals = [v for _, v in spot_series]
    n = len(spot_vals)

    def _ema(values, period):
        if len(values) < period:
            return None
        k = 2.0 / (period + 1)
        val = sum(values[:period]) / period  # SMA seed
        for v in values[period:]:
            val = v * k + val * (1.0 - k)
        return round(val, 2)

    def _sma(values, period):
        if len(values) < period:
            return None
        return round(sum(values[-period:]) / period, 2)

    def _roc(values, periods):
        if len(values) <= periods:
            return None
        ref = values[-(periods + 1)]
        return None if ref == 0 else round((values[-1] - ref) / ref * 100, 4)

    # ---- Moving averages ----
    sma20  = _sma(spot_vals, 20)
    sma50  = _sma(spot_vals, 50)
    sma200 = _sma(spot_vals, 200)
    ema12  = _ema(spot_vals, 12)
    ema20  = _ema(spot_vals, 20)
    ema26  = _ema(spot_vals, 26)
    ema50  = _ema(spot_vals, 50)
    ema100 = _ema(spot_vals, 100)
    ema_osc = round(ema12 - ema26, 4) if (ema12 is not None and ema26 is not None) else None

    result.update({
        'spot_sma_20':  sma20  if sma20  is not None else '',
        'spot_sma_50':  sma50  if sma50  is not None else '',
        'spot_sma_200': sma200 if sma200 is not None else '',
        'spot_ema_12':  ema12  if ema12  is not None else '',
        'spot_ema_20':  ema20  if ema20  is not None else '',
        'spot_ema_26':  ema26  if ema26  is not None else '',
        'spot_ema_50':  ema50  if ema50  is not None else '',
        'spot_ema_100': ema100 if ema100 is not None else '',
        'spot_ema_osc': ema_osc if ema_osc is not None else '',
    })

    # ---- Bollinger Bands (20-period, 2 standard deviations) ----
    if n >= 20 and sma20 is not None:
        bb_std   = statistics.stdev(spot_vals[-20:])
        bb_upper = round(sma20 + 2 * bb_std, 2)
        bb_lower = round(sma20 - 2 * bb_std, 2)
        bb_width = round((bb_upper - bb_lower) / sma20 * 100, 4)
        result.update({
            'spot_bb_upper':     bb_upper,
            'spot_bb_mid':       sma20,
            'spot_bb_lower':     bb_lower,
            'spot_bb_width_pct': bb_width,
        })
    else:
        result.update({
            'spot_bb_upper': '', 'spot_bb_mid': '',
            'spot_bb_lower': '', 'spot_bb_width_pct': '',
        })

    # ---- Rate of Change ----
    roc_21 = _roc(spot_vals, 21)
    roc_63 = _roc(spot_vals, 63)

    cur    = spot_vals[-1]
    at_24h = next(((ts, v) for ts, v in spot_series if ts >= cutoff_24h), None)
    at_7d  = next(((ts, v) for ts, v in spot_series if ts >= cutoff_7d),  None)
    roc_24h = round((cur - at_24h[1]) / at_24h[1] * 100, 4) if at_24h and at_24h[1] else None
    roc_7d  = round((cur - at_7d[1])  / at_7d[1]  * 100, 4) if at_7d  and at_7d[1]  else None

    result.update({
        'spot_roc_24h': roc_24h if roc_24h is not None else '',
        'spot_roc_7d':  roc_7d  if roc_7d  is not None else '',
        'spot_roc_21':  roc_21  if roc_21  is not None else '',
        'spot_roc_63':  roc_63  if roc_63  is not None else '',
    })

    # ---- TIMID Score (Weldon 2007, Gold Trading Boot Camp, ch.34) ----
    # Component truth table (each 0 or 1):
    # C1: price > EMA100      (long-term trend filter)
    # C2: EMA50 > EMA100      (golden/death cross — trend structure)
    # C3: EMA20 > SMA20       (momentum acceleration: recent price leads)
    # C4: ROC21 > 0           (price higher than 21 periods ago = uptrend)
    # C5: ROC21 > ROC63       (short-term momentum accelerating vs long-term)
    t1 = int(ema100 is not None and cur > ema100)
    t2 = int(ema50  is not None and ema100 is not None and ema50  > ema100)
    t3 = int(ema20  is not None and sma20  is not None and ema20  > sma20)
    t4 = int(roc_21 is not None and roc_21 > 0)
    t5 = int(roc_21 is not None and roc_63 is not None and roc_21 > roc_63)
    timid_score = t1 + t2 + t3 + t4 + t5
    timid_zone  = ('NO_TREND' if timid_score <= 1 else
                   'EMERGING' if timid_score == 2 else
                   'DOMINANT' if timid_score <= 4 else
                   'EXTENDED')

    result.update({
        'timid_c1_price_gt_ema100': t1,
        'timid_c2_ema50_gt_ema100': t2,
        'timid_c3_ema20_gt_sma20':  t3,
        'timid_c4_roc21_positive':  t4,
        'timid_c5_roc21_gt_roc63':  t5,
        'timid_score':              timid_score,
        'timid_zone':               timid_zone,
    })

    print(f"  TIMID: {timid_score}/5 ({timid_zone})  C1={t1} C2={t2} C3={t3} C4={t4} C5={t5}")
    print(f"  BB: {result.get('spot_bb_lower', '?')} / {result.get('spot_bb_mid', '?')} / {result.get('spot_bb_upper', '?')}")
    print(f"  EMA osc: {ema_osc}  ROC21: {roc_21}  ROC63: {roc_63}")

    return result


# =============================================================================
# CORRELATED ASSETS (yfinance)
# =============================================================================

_CORR_TICKERS = {
    'XAG=X':   'xag_usd',
    '^VIX':    'vix',
    'DX=F':    'dxy',
    '^GSPC':   'spx',
    'CL=F':    'wti_oil',
    'BTC-USD': 'btc_usd',
    'XPT=X':   'xpt_usd',
}


def fetch_correlated_assets():
    """Fetch last price for silver, VIX, DXY, SPX, crude oil, BTC, platinum via yfinance."""
    empty = {col: '' for col in _CORR_TICKERS.values()}
    try:
        import yfinance as yf
        result = {}
        for ticker, col in _CORR_TICKERS.items():
            try:
                price = yf.Ticker(ticker).fast_info.last_price
                result[col] = round(float(price), 4) if price is not None else ''
                if result[col] != '':
                    print(f"  {col}: {result[col]}")
            except Exception as e:
                print(f"  {ticker} failed: {e}")
                result[col] = ''
        return result
    except Exception as e:
        print(f"  Correlated assets fetch failed: {e}")
        return empty


# =============================================================================
# US TREASURY YIELDS (yfinance)
# =============================================================================

_RATE_TICKERS = {
    '^IRX': 'ust_3m',   # 13-week T-bill (short rate proxy)
    '^TNX': 'ust_10y',  # 10-year Treasury note yield
    '^TYX': 'ust_30y',  # 30-year Treasury bond yield
}


def fetch_rates():
    """Fetch US Treasury yields (3M, 10Y, 30Y) via yfinance. Values in %."""
    empty = {col: '' for col in _RATE_TICKERS.values()}
    try:
        import yfinance as yf
        result = {}
        for ticker, col in _RATE_TICKERS.items():
            try:
                price = yf.Ticker(ticker).fast_info.last_price
                result[col] = round(float(price), 4) if price is not None else ''
                if result[col] != '':
                    print(f"  {col}: {result[col]}%")
            except Exception as e:
                print(f"  {ticker} failed: {e}")
                result[col] = ''
        return result
    except Exception as e:
        print(f"  Rates fetch failed: {e}")
        return empty


# =============================================================================
# COT DATA (CFTC Disaggregated, weekly)
# =============================================================================

_COT_KEYS = [
    'cot_date', 'cot_noncomm_long', 'cot_noncomm_short', 'cot_noncomm_net',
    'cot_comm_long', 'cot_comm_short', 'cot_comm_net',
]


def _get_last_cot_from_csv(csv_file):
    """Return the most recent non-empty COT row dict from the annual CSV, or None."""
    if not os.path.exists(csv_file):
        return None
    try:
        with open(csv_file, 'r', newline='') as f:
            rows = list(csv.DictReader(f))
        for row in reversed(rows):
            if row.get('cot_date'):
                return {k: row.get(k, '') for k in _COT_KEYS}
    except Exception:
        pass
    return None


def fetch_cot_data(annual_csv_file):
    """Return CFTC Disaggregated COT for COMEX Gold 100 Troy Oz (code 088691).

    Downloads fresh data on Fridays (CFTC release day ~15:30 ET); returns the
    most recently stored row from the CSV on all other days to avoid unnecessary
    traffic to the CFTC server on a weekly-updating dataset.
    """
    now   = datetime.now(timezone.utc)
    empty = {k: '' for k in _COT_KEYS}

    cached = _get_last_cot_from_csv(annual_csv_file)

    # Skip download on non-Fridays when we already have cached data
    if now.weekday() != 4 and cached:
        print(f"  COT cached: date={cached.get('cot_date')}  net non-comm={cached.get('cot_noncomm_net')}")
        return cached

    try:
        url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txtonly_{now.year}.zip"
        resp = requests.get(url, headers=HEADERS, timeout=45)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            fname = next(n for n in z.namelist() if n.lower().endswith('.txt'))
            with z.open(fname) as f:
                content = f.read().decode('latin-1')

        gold_rows = []
        for row in csv.DictReader(io.StringIO(content)):
            code = row.get('CFTC_Contract_Market_Code', '')
            name = row.get('Market_and_Exchange_Names', '').upper()
            if CFTC_GOLD_CODE in code or ('GOLD' in name and '100 TROY' in name):
                gold_rows.append(row)

        if not gold_rows:
            print("  COT: GOLD 100 Troy Oz rows not found in CFTC file")
            return cached or empty

        latest = gold_rows[-1]

        def _int(key):
            try:
                return int(str(latest.get(key, '0')).replace(',', '').strip() or '0')
            except (ValueError, TypeError):
                return ''

        nc_long  = _int('NonComm_Positions_Long_All')
        nc_short = _int('NonComm_Positions_Short_All')
        c_long   = _int('Comm_Positions_Long_All')
        c_short  = _int('Comm_Positions_Short_All')
        nc_net   = nc_long  - nc_short if isinstance(nc_long,  int) and isinstance(nc_short, int) else ''
        c_net    = c_long   - c_short  if isinstance(c_long,   int) and isinstance(c_short,  int) else ''

        cot_date = latest.get('Report_Date_as_YYYY-MM-DD', '')
        print(f"  COT fresh: date={cot_date}  net non-comm={nc_net}  net comm={c_net}")

        return {
            'cot_date':          cot_date,
            'cot_noncomm_long':  nc_long,
            'cot_noncomm_short': nc_short,
            'cot_noncomm_net':   nc_net,
            'cot_comm_long':     c_long,
            'cot_comm_short':    c_short,
            'cot_comm_net':      c_net,
        }

    except Exception as e:
        print(f"  COT download failed: {e}")
        return cached or empty


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("FETCHING GOLD PRICES FROM MULTIPLE SOURCES")
    print("=" * 60)

    # Define CSV paths early — needed by technical indicators and COT caching
    os.makedirs('data', exist_ok=True)
    month_key       = datetime.now(timezone.utc).strftime('%Y-%m')
    year_key        = datetime.now(timezone.utc).strftime('%Y')
    csv_file        = f'data/{month_key}.csv'
    annual_csv_file = f'data/{year_key}.csv'

    # --- [1/9] UOB Prices ---
    print("\n[1/9] Fetching UOB 1kg cast bar, 100g argor, and GSA prices...")
    print("  URL: https://www.uobgroup.com/wsm/gold-silver")
    uob_data = fetch_uob_prices()
    if uob_data['success']:
        print(f"  UOB: Success via {uob_data.get('source', 'unknown')}")
    else:
        print(f"  UOB: Failed - {uob_data.get('error', 'unknown')}")

    # --- [2/9] Gold Spot Source A ---
    print("\n[2/9] Fetching XAUUSD from CNBC...")
    gold_a = fetch_cnbc_gold()
    if gold_a['success']:
        print(f"  CNBC Gold: ${gold_a['price']:.2f}/oz")
    else:
        print(f"  CNBC Gold: Failed - {gold_a.get('error', 'unknown')}")

    # --- [3/9] Gold Spot Source B ---
    print("\n[3/9] Fetching XAUUSD from GoldPrice.org (OTC, with GC=F fallback)...")
    gold_b = fetch_goldprice_org()
    if gold_b['success']:
        print(f"  {gold_b['source']}: ${gold_b['price']:.2f}/oz")
    else:
        print(f"  GoldPrice.org/GC=F: Failed - {gold_b.get('error', 'unknown')}")

    # --- [4/9] Forex Source A (also returns all currency rates) ---
    print("\n[4/9] Fetching USD/SGD + multi-currency rates from ExchangeRate-API...")
    forex_a = fetch_exchangerate_api_usdsgd()
    if forex_a['success']:
        print(f"  ExchangeRate-API: {forex_a['rate']:.4f}")
    else:
        print(f"  ExchangeRate-API: Failed - {forex_a.get('error', 'unknown')}")

    # --- [5/9] Forex Source B ---
    print("\n[5/9] Fetching USD/SGD from Frankfurter...")
    forex_b = fetch_frankfurter_usdsgd()
    if forex_b['success']:
        print(f"  Frankfurter: {forex_b['rate']:.4f}")
    else:
        print(f"  Frankfurter: Failed - {forex_b.get('error', 'unknown')}")

    # --- [6/9] Technical Indicators ---
    print("\n[6/9] Computing technical indicators from CSV history...")
    ta = compute_technical_indicators(annual_csv_file)
    if ta:
        print(f"  {len(ta)} indicator values computed")
    else:
        print("  No indicators computed (insufficient history)")

    # --- [7/9] Correlated Assets ---
    print("\n[7/9] Fetching correlated assets (Silver, VIX, DXY, SPX, Oil, BTC, Platinum)...")
    corr = fetch_correlated_assets()

    # --- [8/9] Treasury Yields ---
    print("\n[8/9] Fetching US Treasury yields (3M, 10Y, 30Y)...")
    rates = fetch_rates()

    # --- [9/9] COT Data ---
    print("\n[9/9] Fetching CFTC COT data for COMEX Gold...")
    cot = fetch_cot_data(annual_csv_file)

    # =================================================================
    # AGGREGATION & VALIDATION
    # =================================================================
    print("\n" + "=" * 60)
    print("AGGREGATING DATA WITH CROSS-VALIDATION")
    print("=" * 60)

    gold_sources_data = []
    for src in [gold_a, gold_b]:
        if src.get('success'):
            gold_sources_data.append(src)

    gold_spot_avg = None
    if len(gold_sources_data) >= 2:
        prices = [s['price'] for s in gold_sources_data]
        gold_spot_avg = sum(prices) / len(prices)
        print(f"\n  Gold Spot: 2 sources agree -> avg ${gold_spot_avg:.2f}/oz")
    elif len(gold_sources_data) == 1:
        gold_spot_avg = gold_sources_data[0]['price']
        print(f"\n  Gold Spot: Only 1 source available ({gold_sources_data[0]['source']}): ${gold_spot_avg:.2f}/oz")
        print(f"  WARNING: Cannot cross-validate with only 1 source")
    else:
        print(f"\n  Gold Spot: {NO_DATA}")

    forex_sources_data = []
    for src in [forex_a, forex_b]:
        if src.get('success'):
            forex_sources_data.append(src)

    forex_avg = None
    if len(forex_sources_data) >= 2:
        rates_list = [s['rate'] for s in forex_sources_data]
        forex_avg = sum(rates_list) / len(rates_list)
        print(f"  USD/SGD: 2 sources agree -> avg {forex_avg:.4f}")
    elif len(forex_sources_data) == 1:
        forex_avg = forex_sources_data[0]['rate']
        print(f"  USD/SGD: Only 1 source available ({forex_sources_data[0]['source']}): {forex_avg:.4f}")
        print(f"  WARNING: Cannot cross-validate with only 1 source")
    else:
        print(f"  USD/SGD: {NO_DATA}")

    # Gold in 10 currencies (per troy oz, using ExchangeRate-API rates)
    all_fx_rates = forex_a.get('rates', {}) if forex_a.get('success') else {}
    xau_currencies = {}
    if gold_spot_avg and all_fx_rates:
        for ccy in GOLD_CURRENCIES:
            rate = all_fx_rates.get(ccy)
            xau_currencies[f'xau_{ccy.lower()}'] = round(gold_spot_avg * rate, 2) if rate else ''
    else:
        for ccy in GOLD_CURRENCIES:
            xau_currencies[f'xau_{ccy.lower()}'] = ''

    # =================================================================
    # BUILD RESULT JSON
    # =================================================================
    result = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'uob_prices_sgd': uob_data.get('prices', {}) if uob_data['success'] else NO_DATA,
        'gold_spot_usd_per_oz': {
            'average': round(gold_spot_avg, 2) if gold_spot_avg else NO_DATA,
            'sources': {
                'cnbc': gold_a.get('price', 0) if gold_a['success'] else NO_DATA,
                'yahoo': gold_b.get('price', 0) if gold_b['success'] else NO_DATA,
            },
            'source_count': len(gold_sources_data),
            'cross_validated': len(gold_sources_data) >= 2
        },
        'usd_sgd_rate': {
            'average': round(forex_avg, 4) if forex_avg else NO_DATA,
            'sources': {
                'exchangerate_api': forex_a.get('rate', 0) if forex_a['success'] else NO_DATA,
                'frankfurter': forex_b.get('rate', 0) if forex_b['success'] else NO_DATA,
            },
            'source_count': len(forex_sources_data),
            'cross_validated': len(forex_sources_data) >= 2
        },
        'status': {
            'uob_success': uob_data.get('success', False),
            'gold_spot_sources': len(gold_sources_data),
            'forex_sources': len(forex_sources_data),
            'gold_cross_validated': len(gold_sources_data) >= 2,
            'forex_cross_validated': len(forex_sources_data) >= 2,
        },
        'errors': {}
    }

    if not uob_data['success']:
        result['errors']['uob'] = uob_data.get('error', 'unknown')
    if not gold_a['success']:
        result['errors']['cnbc_gold'] = gold_a.get('error', 'unknown')
    if not gold_b['success']:
        result['errors']['yahoo_gold'] = gold_b.get('error', 'unknown')
    if not forex_a['success']:
        result['errors']['exchangerate_api'] = forex_a.get('error', 'unknown')
    if not forex_b['success']:
        result['errors']['frankfurter'] = forex_b.get('error', 'unknown')

    if gold_spot_avg and forex_avg:
        sgd_per_gram = (gold_spot_avg * forex_avg) / 31.1035

        result['calculated'] = {
            'spot_price_sgd_per_gram': round(sgd_per_gram, 2),
            'spot_price_sgd_per_kg': round(sgd_per_gram * 1000, 2)
        }

        if uob_data.get('prices', {}).get('1kg_cast_buy'):
            uob_buy = uob_data['prices']['1kg_cast_buy']
            spot_kg = result['calculated']['spot_price_sgd_per_kg']

            premium = uob_buy - spot_kg
            premium_pct = (premium / spot_kg) * 100

            result['calculated']['uob_1kg_premium_sgd'] = round(premium, 2)
            result['calculated']['uob_1kg_premium_percent'] = round(premium_pct, 2)

            if uob_data['prices'].get('1kg_cast_sell'):
                spread = uob_data['prices']['1kg_cast_buy'] - uob_data['prices']['1kg_cast_sell']
                spread_pct = (spread / uob_data['prices']['1kg_cast_buy']) * 100
                result['calculated']['uob_spread_sgd'] = round(spread, 2)
                result['calculated']['uob_spread_percent'] = round(spread_pct, 2)

    with open('gold_prices.json', 'w') as f:
        json.dump(result, f, indent=2)

    print("\nData saved to gold_prices.json")

    # =================================================================
    # APPEND TO history_2026.json
    # =================================================================
    history_file = 'history_2026.json'
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        else:
            history = []
        history.append(result)
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        print(f"Data appended to {history_file} ({len(history)} records total)")
    except Exception as e:
        print(f"Failed to update {history_file}: {e}")

    # =================================================================
    # BUILD CSV ROW
    # =================================================================
    uob  = result.get('uob_prices_sgd', {})
    gold = result.get('gold_spot_usd_per_oz', {})
    forex = result.get('usd_sgd_rate', {})
    calc = result.get('calculated', {})

    # Detect staleness before building the row (reads existing CSV tail)
    spot_stale = detect_spot_stale(csv_file, gold_spot_avg)
    if spot_stale:
        print(f"  Spot price appears stale (unchanged for {STALE_CONSEC_RUNS}+ runs)")

    # GSA spread
    _gsa_sell = uob.get('gsa_sell') if isinstance(uob, dict) else None
    _gsa_buy  = uob.get('gsa_buy')  if isinstance(uob, dict) else None
    if _gsa_sell and _gsa_buy and _gsa_sell > 0:
        _gsa_spread_pct = round((_gsa_sell - _gsa_buy) / _gsa_sell * 100, 2)
    else:
        _gsa_spread_pct = ''

    full_row = {
        # ── Core prices ──────────────────────────────────────────────
        'timestamp':               result['last_updated'],
        'uob_100g_buy':            uob.get('100g_cast_buy', '')       if isinstance(uob, dict)  else '',
        'uob_100g_sell':           uob.get('100g_cast_sell', '')      if isinstance(uob, dict)  else '',
        'uob_1kg_buy':             uob.get('1kg_cast_buy', '')        if isinstance(uob, dict)  else '',
        'uob_1kg_sell':            uob.get('1kg_cast_sell', '')       if isinstance(uob, dict)  else '',
        'gold_spot_usd_avg':       gold.get('average', '')            if isinstance(gold, dict) else '',
        'gold_spot_cnbc':          gold.get('sources', {}).get('cnbc', '')   if isinstance(gold, dict) else '',
        'gold_spot_goldprice_org': gold.get('sources', {}).get('yahoo', '')  if isinstance(gold, dict) else '',
        'gold_cross_validated':    gold.get('cross_validated', '')    if isinstance(gold, dict) else '',
        'usdsgd_avg':              forex.get('average', '')           if isinstance(forex, dict) else '',
        'usdsgd_exchangerate_api': forex.get('sources', {}).get('exchangerate_api', '') if isinstance(forex, dict) else '',
        'usdsgd_frankfurter':      forex.get('sources', {}).get('frankfurter', '')      if isinstance(forex, dict) else '',
        'forex_cross_validated':   forex.get('cross_validated', '')   if isinstance(forex, dict) else '',
        'spot_sgd_per_gram':       calc.get('spot_price_sgd_per_gram', ''),
        'spot_sgd_per_kg':         calc.get('spot_price_sgd_per_kg', ''),
        'uob_1kg_premium_sgd':     calc.get('uob_1kg_premium_sgd', ''),
        'uob_1kg_premium_pct':     calc.get('uob_1kg_premium_percent', ''),
        'uob_spread_sgd':          calc.get('uob_spread_sgd', ''),
        'uob_spread_pct':          calc.get('uob_spread_percent', ''),
        'spot_stale':              spot_stale,
        # ── UOB GSA ──────────────────────────────────────────────────
        'uob_gsa_sell':            _gsa_sell if _gsa_sell is not None else '',
        'uob_gsa_buy':             _gsa_buy  if _gsa_buy  is not None else '',
        'uob_gsa_spread_pct':      _gsa_spread_pct,
        # ── 24H OHLR — spot XAU/USD ──────────────────────────────────
        'spot_24h_open':           ta.get('spot_24h_open', ''),
        'spot_24h_high':           ta.get('spot_24h_high', ''),
        'spot_24h_low':            ta.get('spot_24h_low', ''),
        'spot_24h_range':          ta.get('spot_24h_range', ''),
        # ── 24H OHLR — UOB 1kg sell ──────────────────────────────────
        'uob_1kg_24h_open':        ta.get('uob_1kg_24h_open', ''),
        'uob_1kg_24h_high':        ta.get('uob_1kg_24h_high', ''),
        'uob_1kg_24h_low':         ta.get('uob_1kg_24h_low', ''),
        'uob_1kg_24h_range':       ta.get('uob_1kg_24h_range', ''),
        # ── 24H OHLR — UOB GSA sell ──────────────────────────────────
        'uob_gsa_24h_open':        ta.get('uob_gsa_24h_open', ''),
        'uob_gsa_24h_high':        ta.get('uob_gsa_24h_high', ''),
        'uob_gsa_24h_low':         ta.get('uob_gsa_24h_low', ''),
        'uob_gsa_24h_range':       ta.get('uob_gsa_24h_range', ''),
        # ── Bollinger Bands (20-period, 2 std dev on gold_spot_usd_avg) ─
        'spot_bb_upper':           ta.get('spot_bb_upper', ''),
        'spot_bb_mid':             ta.get('spot_bb_mid', ''),
        'spot_bb_lower':           ta.get('spot_bb_lower', ''),
        'spot_bb_width_pct':       ta.get('spot_bb_width_pct', ''),
        # ── Simple moving averages ────────────────────────────────────
        'spot_sma_20':             ta.get('spot_sma_20', ''),
        'spot_sma_50':             ta.get('spot_sma_50', ''),
        'spot_sma_200':            ta.get('spot_sma_200', ''),
        # ── Exponential moving averages ───────────────────────────────
        'spot_ema_12':             ta.get('spot_ema_12', ''),
        'spot_ema_20':             ta.get('spot_ema_20', ''),
        'spot_ema_26':             ta.get('spot_ema_26', ''),
        'spot_ema_50':             ta.get('spot_ema_50', ''),
        'spot_ema_100':            ta.get('spot_ema_100', ''),
        # ── EMA oscillator (EMA12 - EMA26) ───────────────────────────
        'spot_ema_osc':            ta.get('spot_ema_osc', ''),
        # ── Rate of change ────────────────────────────────────────────
        'spot_roc_24h':            ta.get('spot_roc_24h', ''),
        'spot_roc_7d':             ta.get('spot_roc_7d', ''),
        'spot_roc_21':             ta.get('spot_roc_21', ''),
        'spot_roc_63':             ta.get('spot_roc_63', ''),
        # ── TIMID Score (Weldon 2007) ─────────────────────────────────
        'timid_c1_price_gt_ema100': ta.get('timid_c1_price_gt_ema100', ''),
        'timid_c2_ema50_gt_ema100': ta.get('timid_c2_ema50_gt_ema100', ''),
        'timid_c3_ema20_gt_sma20':  ta.get('timid_c3_ema20_gt_sma20', ''),
        'timid_c4_roc21_positive':  ta.get('timid_c4_roc21_positive', ''),
        'timid_c5_roc21_gt_roc63':  ta.get('timid_c5_roc21_gt_roc63', ''),
        'timid_score':              ta.get('timid_score', ''),
        'timid_zone':               ta.get('timid_zone', ''),
        # ── Gold in 10 currencies (per troy oz) ──────────────────────
        'xau_eur':                 xau_currencies.get('xau_eur', ''),
        'xau_gbp':                 xau_currencies.get('xau_gbp', ''),
        'xau_jpy':                 xau_currencies.get('xau_jpy', ''),
        'xau_aud':                 xau_currencies.get('xau_aud', ''),
        'xau_cad':                 xau_currencies.get('xau_cad', ''),
        'xau_chf':                 xau_currencies.get('xau_chf', ''),
        'xau_cny':                 xau_currencies.get('xau_cny', ''),
        'xau_inr':                 xau_currencies.get('xau_inr', ''),
        'xau_hkd':                 xau_currencies.get('xau_hkd', ''),
        'xau_sgd':                 xau_currencies.get('xau_sgd', ''),
        # ── Correlated assets ─────────────────────────────────────────
        'xag_usd':                 corr.get('xag_usd', ''),
        'vix':                     corr.get('vix', ''),
        'dxy':                     corr.get('dxy', ''),
        'spx':                     corr.get('spx', ''),
        'wti_oil':                 corr.get('wti_oil', ''),
        'btc_usd':                 corr.get('btc_usd', ''),
        'xpt_usd':                 corr.get('xpt_usd', ''),
        # ── US Treasury yields (%) ────────────────────────────────────
        'ust_3m':                  rates.get('ust_3m', ''),
        'ust_10y':                 rates.get('ust_10y', ''),
        'ust_30y':                 rates.get('ust_30y', ''),
        # ── CFTC COT — COMEX Gold 100 Troy Oz ────────────────────────
        'cot_date':                cot.get('cot_date', ''),
        'cot_noncomm_long':        cot.get('cot_noncomm_long', ''),
        'cot_noncomm_short':       cot.get('cot_noncomm_short', ''),
        'cot_noncomm_net':         cot.get('cot_noncomm_net', ''),
        'cot_comm_long':           cot.get('cot_comm_long', ''),
        'cot_comm_short':          cot.get('cot_comm_short', ''),
        'cot_comm_net':            cot.get('cot_comm_net', ''),
    }

    # =================================================================
    # WRITE TO CSVs (idempotent header migration)
    # =================================================================
    def _write_csv(target_csv):
        try:
            existing_fieldnames = get_csv_fieldnames(target_csv)
            file_exists = existing_fieldnames is not None
            new_fieldnames = list(full_row.keys())
            missing_cols = [f for f in new_fieldnames if f not in (existing_fieldnames or [])]

            if file_exists and missing_cols:
                # Idempotent migration: all concurrent workflows write the same
                # fixed string, so repeated execution cannot compound the header.
                with open(target_csv, 'r', newline='') as f:
                    content = f.read()
                old_header = content.split('\n')[0]
                new_header = ','.join(new_fieldnames)
                content = new_header + content[len(old_header):]
                with open(target_csv, 'w', newline='') as f:
                    f.write(content)
                print(f"  Updated header of existing {target_csv}")
                with open(target_csv, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                    writer.writerow(full_row)
            else:
                with open(target_csv, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(full_row)

            print(f"Data appended to {target_csv}")
        except Exception as e:
            print(f"Failed to update {target_csv}: {e}")

    _write_csv(csv_file)
    _write_csv(annual_csv_file)

    # =================================================================
    # SUMMARY
    # =================================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nUOB Prices:")
    if uob_data['success'] and uob_data.get('prices'):
        if uob_data['prices'].get('1kg_cast_buy'):
            print(f"  1kg Cast - Buy: ${uob_data['prices']['1kg_cast_buy']:,.2f} SGD")
        if uob_data['prices'].get('1kg_cast_sell'):
            print(f"  1kg Cast - Sell: ${uob_data['prices']['1kg_cast_sell']:,.2f} SGD")
        if uob_data['prices'].get('100g_cast_buy'):
            print(f"  100g Argor - Buy: ${uob_data['prices']['100g_cast_buy']:,.2f} SGD")
        if uob_data['prices'].get('100g_cast_sell'):
            print(f"  100g Argor - Sell: ${uob_data['prices']['100g_cast_sell']:,.2f} SGD")
        if uob_data['prices'].get('gsa_sell') and uob_data['prices'].get('gsa_buy'):
            print(f"  GSA - Sell: ${uob_data['prices']['gsa_sell']:.4f} SGD/gram  Buy: ${uob_data['prices']['gsa_buy']:.4f} SGD/gram")
        else:
            print(f"  GSA: {NO_DATA}")
    else:
        print(f"  {NO_DATA}")

    print(f"\nGold Spot (USD/oz):")
    print(f"  CNBC: ${gold_a['price']:.2f}" if gold_a['success'] else f"  CNBC: {NO_DATA}")
    print(f"  {gold_b['source']}: ${gold_b['price']:.2f}" if gold_b['success'] else f"  GoldPrice.org: {NO_DATA}")
    if gold_spot_avg:
        print(f"  Average: ${gold_spot_avg:.2f}/oz  (stale={spot_stale})")
    else:
        print(f"  Average: {NO_DATA}")

    print(f"\nUSD/SGD Rate:")
    print(f"  ExchangeRate-API: {forex_a['rate']:.4f}" if forex_a['success'] else f"  ExchangeRate-API: {NO_DATA}")
    print(f"  Frankfurter: {forex_b['rate']:.4f}" if forex_b['success'] else f"  Frankfurter: {NO_DATA}")
    if forex_avg:
        print(f"  Average: {forex_avg:.4f}")

    if result.get('calculated'):
        c = result['calculated']
        print(f"\nCalculated:")
        print(f"  ${c['spot_price_sgd_per_gram']:.2f}/gram SGD  |  ${c['spot_price_sgd_per_kg']:,.2f}/kg SGD")
        if c.get('uob_1kg_premium_sgd') is not None:
            print(f"  UOB 1kg Premium: ${c['uob_1kg_premium_sgd']:,.2f} ({c['uob_1kg_premium_percent']:.2f}%)")
        if c.get('uob_spread_sgd') is not None:
            print(f"  UOB Spread: ${c['uob_spread_sgd']:,.2f} ({c['uob_spread_percent']:.2f}%)")

    if ta.get('timid_score') != '':
        print(f"\nTIMID: {ta.get('timid_score')}/5 ({ta.get('timid_zone')})")

    if xau_currencies.get('xau_eur'):
        print("\nGold per troy oz:")
        for ccy in GOLD_CURRENCIES:
            val = xau_currencies.get(f'xau_{ccy.lower()}', '')
            if val:
                print(f"  XAU/{ccy}: {val:,.2f}")

    print("\n" + "=" * 60)

    gold_ok  = len(gold_sources_data) >= 2
    forex_ok = len(forex_sources_data) >= 2
    if gold_ok:
        print("Gold spot: 2 sources verified")
    else:
        print(f"Gold spot: Only {len(gold_sources_data)} source(s) - need 2 for validation")
    if forex_ok:
        print("Forex USD/SGD: 2 sources verified")
    else:
        print(f"Forex USD/SGD: Only {len(forex_sources_data)} source(s) - need 2 for validation")
    if spot_stale:
        print(f"Spot price stale: same value for {STALE_CONSEC_RUNS}+ consecutive runs")
    if uob_data['success']:
        print("UOB prices fetched successfully")
    else:
        print(f"UOB prices: {NO_DATA}")

    if len(gold_sources_data) == 0 or len(forex_sources_data) == 0:
        print("\nCRITICAL: Missing gold spot or forex data entirely")
        sys.exit(1)


if __name__ == '__main__':
    main()
