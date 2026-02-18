#!/usr/bin/env python3
"""
Fetch UOB gold prices, spot gold price, and USD/SGD exchange rate
Runs every 10 minutes via GitHub Actions

Sources:
1. UOB gold bar prices (JSON API - UPDATED TO MATCH keju30.py)
   https://www.uobgroup.com/wsm/gold-silver
2. Gold spot XAUUSD - Source A: CNBC (web scraping)
3. Gold spot XAUUSD - Source B: GoldPrice.org (JSON API)
4. USD/SGD forex - Source A: ExchangeRate-API (JSON API)
5. USD/SGD forex - Source B: Frankfurter (JSON API, ECB data)
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

NO_DATA = 'No Data'


# =============================================================================
# UOB GOLD PRICES - UPDATED IMPLEMENTATION
# =============================================================================

def fetch_uob_prices():
    """Fetch UOB cast 1kg and 100g gold bar prices from the JSON API.
    Source: https://www.uobgroup.com/wsm/gold-silver
    Implementation based on keju30.py working approach
    """
    errors = []

    try:
        url = "https://www.uobgroup.com/wsm/gold-silver"
        headers = {**HEADERS, 'Referer': 'https://www.uobgroup.com/online-rates/gold-and-silver-prices.page'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        argor_data = None
        cast_data = None

        # The API returns a 'types' array with product information
        for item in data.get('types', []):
            description = str(item.get('description', '')).upper()
            unit = str(item.get('unit', '')).upper()

            try:
                buy_price = float(item.get('bankBuy', 0))
                sell_price = float(item.get('bankSell', 0))

                # Look for Argor 100g Cast Bar (ACB = Argor Cast Bar)
                if description == 'ACB' and '100 GM' in unit:
                    argor_data = {
                        'buy': buy_price,
                        'sell': sell_price,
                        'description': 'Argor 100g Cast Bar'
                    }
                    print(f"  ✓ Found: Argor 100g - Buy {buy_price}, Sell {sell_price}")

                # Look for Cast 1kg Bar (CTB = Cast Bar)
                elif description == 'CTB' and '1 KILOBAR' in unit:
                    cast_data = {
                        'buy': buy_price,
                        'sell': sell_price,
                        'description': 'Cast 1kg Bar'
                    }
                    print(f"  ✓ Found: Cast 1kg - Buy {buy_price}, Sell {sell_price}")

            except (ValueError, TypeError) as e:
                print(f"  ⚠ Price parsing error for item: {e}")
                continue

        # Return success only if we found both products
        if argor_data and cast_data:
            return {
                'success': True,
                'prices': {
                    '100g_cast_buy': argor_data['buy'],
                    '100g_cast_sell': argor_data['sell'],
                    '1kg_cast_buy': cast_data['buy'],
                    '1kg_cast_sell': cast_data['sell']
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
    """Gold spot source B: GoldPrice.org JSON API (free, no key)"""
    try:
        url = "https://data-asg.goldprice.org/dbXRates/USD"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        price = float(data.get('items', [{}])[0].get('xauPrice', 0))

        if price and 1000 < price < 10000:
            return {'success': True, 'price': price, 'source': 'GoldPrice.org'}

        return {'success': False, 'error': f'Price out of range or missing: {price}', 'price': 0}

    except Exception as e:
        return {'success': False, 'error': str(e), 'price': 0}


# =============================================================================
# USD/SGD FOREX - 2 SOURCES
# =============================================================================

def fetch_exchangerate_api_usdsgd():
    """Forex source A: ExchangeRate-API (free, no key)"""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('result') == 'success':
            rate = float(data['rates']['SGD'])
            if 1.0 < rate < 2.0:
                return {'success': True, 'rate': rate, 'source': 'ExchangeRate-API'}

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
# MAIN
# =============================================================================

def main():
    """Main function to fetch all data and save to JSON"""
    print("=" * 60)
    print("FETCHING GOLD PRICES FROM MULTIPLE SOURCES")
    print("=" * 60)

    # --- UOB Prices ---
    print("\n[1/5] Fetching UOB 1kg cast bar and 100g argor prices...")
    print("  URL: https://www.uobgroup.com/wsm/gold-silver")
    uob_data = fetch_uob_prices()
    if uob_data['success']:
        print(f"  ✓ UOB: Success via {uob_data.get('source', 'unknown')}")
    else:
        print(f"  ✗ UOB: Failed - {uob_data.get('error', 'unknown')}")

    # --- Gold Spot Source A ---
    print("\n[2/5] Fetching XAUUSD from CNBC...")
    gold_a = fetch_cnbc_gold()
    if gold_a['success']:
        print(f"  ✓ CNBC Gold: ${gold_a['price']:.2f}/oz")
    else:
        print(f"  ✗ CNBC Gold: Failed - {gold_a.get('error', 'unknown')}")

    # --- Gold Spot Source B ---
    print("\n[3/5] Fetching XAUUSD from GoldPrice.org...")
    gold_b = fetch_goldprice_org()
    if gold_b['success']:
        print(f"  ✓ GoldPrice.org Gold: ${gold_b['price']:.2f}/oz")
    else:
        print(f"  ✗ GoldPrice.org Gold: Failed - {gold_b.get('error', 'unknown')}")

    # --- Forex Source A ---
    print("\n[4/5] Fetching USD/SGD from ExchangeRate-API...")
    forex_a = fetch_exchangerate_api_usdsgd()
    if forex_a['success']:
        print(f"  ✓ ExchangeRate-API: {forex_a['rate']:.4f}")
    else:
        print(f"  ✗ ExchangeRate-API: Failed - {forex_a.get('error', 'unknown')}")

    # --- Forex Source B ---
    print("\n[5/5] Fetching USD/SGD from Frankfurter...")
    forex_b = fetch_frankfurter_usdsgd()
    if forex_b['success']:
        print(f"  ✓ Frankfurter: {forex_b['rate']:.4f}")
    else:
        print(f"  ✗ Frankfurter: Failed - {forex_b.get('error', 'unknown')}")

    # =================================================================
    # AGGREGATION & VALIDATION
    # =================================================================
    print("\n" + "=" * 60)
    print("AGGREGATING DATA WITH CROSS-VALIDATION")
    print("=" * 60)

    # Collect gold spot prices from both sources
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
        print(f"  ⚠ WARNING: Cannot cross-validate with only 1 source")
    else:
        print(f"\n  Gold Spot: {NO_DATA}")

    # Collect forex rates from both sources
    forex_sources_data = []
    for src in [forex_a, forex_b]:
        if src.get('success'):
            forex_sources_data.append(src)

    forex_avg = None
    if len(forex_sources_data) >= 2:
        rates = [s['rate'] for s in forex_sources_data]
        forex_avg = sum(rates) / len(rates)
        print(f"  USD/SGD: 2 sources agree -> avg {forex_avg:.4f}")
    elif len(forex_sources_data) == 1:
        forex_avg = forex_sources_data[0]['rate']
        print(f"  USD/SGD: Only 1 source available ({forex_sources_data[0]['source']}): {forex_avg:.4f}")
        print(f"  ⚠ WARNING: Cannot cross-validate with only 1 source")
    else:
        print(f"  USD/SGD: {NO_DATA}")

    # =================================================================
    # BUILD RESULT JSON
    # =================================================================
    result = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'uob_prices_sgd': uob_data.get('prices', {}) if uob_data['success'] else NO_DATA,
        'gold_spot_usd_per_oz': {
            'average': round(gold_spot_avg, 2) if gold_spot_avg else NO_DATA,
            'sources': {
                'cnbc': gold_a.get('price', 0) if gold_a['success'] else NO_DATA,
                'goldprice_org': gold_b.get('price', 0) if gold_b['success'] else NO_DATA,
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

    # Only include errors for failed sources
    if not uob_data['success']:
        result['errors']['uob'] = uob_data.get('error', 'unknown')
    if not gold_a['success']:
        result['errors']['cnbc_gold'] = gold_a.get('error', 'unknown')
    if not gold_b['success']:
        result['errors']['goldprice_org'] = gold_b.get('error', 'unknown')
    if not forex_a['success']:
        result['errors']['exchangerate_api'] = forex_a.get('error', 'unknown')
    if not forex_b['success']:
        result['errors']['frankfurter'] = forex_b.get('error', 'unknown')

    # Calculate derived values ONLY if both gold spot and forex have data
    if gold_spot_avg and forex_avg:
        # 1 troy oz = 31.1035 grams
        sgd_per_gram = (gold_spot_avg * forex_avg) / 31.1035

        result['calculated'] = {
            'spot_price_sgd_per_gram': round(sgd_per_gram, 2),
            'spot_price_sgd_per_kg': round(sgd_per_gram * 1000, 2)
        }

        # Calculate premiums/spreads for UOB prices
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

    # Save to file
    with open('gold_prices.json', 'w') as f:
        json.dump(result, f, indent=2)

    print("\n✓ Data saved to gold_prices.json")

    # =================================================================
    # SUMMARY
    # =================================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # UOB
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
    else:
        print(f"  {NO_DATA}")

    # Gold spot
    print(f"\nGold Spot (USD/oz):")
    if gold_a['success']:
        print(f"  - CNBC: ${gold_a['price']:.2f}")
    else:
        print(f"  - CNBC: {NO_DATA}")
    if gold_b['success']:
        print(f"  - GoldPrice.org: ${gold_b['price']:.2f}")
    else:
        print(f"  - GoldPrice.org: {NO_DATA}")
    if gold_spot_avg:
        print(f"  Average: ${gold_spot_avg:.2f}/oz")
    else:
        print(f"  Average: {NO_DATA}")

    # Forex
    print(f"\nUSD/SGD Rate:")
    if forex_a['success']:
        print(f"  - ExchangeRate-API: {forex_a['rate']:.4f}")
    else:
        print(f"  - ExchangeRate-API: {NO_DATA}")
    if forex_b['success']:
        print(f"  - Frankfurter: {forex_b['rate']:.4f}")
    else:
        print(f"  - Frankfurter: {NO_DATA}")
    if forex_avg:
        print(f"  Average: {forex_avg:.4f}")
    else:
        print(f"  Average: {NO_DATA}")

    # Calculated values
    if result.get('calculated'):
        print(f"\nCalculated Spot Prices:")
        print(f"  ${result['calculated']['spot_price_sgd_per_gram']:.2f}/gram SGD")
        print(f"  ${result['calculated']['spot_price_sgd_per_kg']:,.2f}/kg SGD")

        if result['calculated'].get('uob_1kg_premium_sgd') is not None:
            print(f"\n  UOB 1kg Premium: ${result['calculated']['uob_1kg_premium_sgd']:,.2f} ({result['calculated']['uob_1kg_premium_percent']:.2f}%)")
        if result['calculated'].get('uob_spread_sgd') is not None:
            print(f"  UOB Spread: ${result['calculated']['uob_spread_sgd']:,.2f} ({result['calculated']['uob_spread_percent']:.2f}%)")
    else:
        print(f"\nCalculated Spot Prices: {NO_DATA}")

    print("\n" + "=" * 60)

    # Validation summary
    gold_ok = len(gold_sources_data) >= 2
    forex_ok = len(forex_sources_data) >= 2

    if gold_ok and forex_ok:
        print("✓ Gold spot: 2 sources verified")
        print("✓ Forex USD/SGD: 2 sources verified")
    else:
        if not gold_ok:
            print(f"⚠ Gold spot: Only {len(gold_sources_data)} source(s) - need 2 for validation")
        if not forex_ok:
            print(f"⚠ Forex USD/SGD: Only {len(forex_sources_data)} source(s) - need 2 for validation")

    if uob_data['success']:
        print("✓ UOB prices fetched successfully")
    else:
        print(f"⚠ UOB prices: {NO_DATA}")

    # Exit with error if no gold or forex data at all
    if len(gold_sources_data) == 0 or len(forex_sources_data) == 0:
        print("\n⚠ CRITICAL: Missing gold spot or forex data entirely")
        sys.exit(1)


if __name__ == '__main__':
    main()