#!/usr/bin/env python3
"""
Fetch UOB gold prices, spot gold price, and USD/SGD exchange rate
Runs every 10 minutes via GitHub Actions

Sources:
1. UOB cast 1kg bar prices
2. TradingView XAUUSD spot
3. CNBC XAUUSD spot
4. CNBC USD/SGD
5. Yahoo Finance USD/SGD
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_uob_prices():
    """Fetch UOB cast 1kg gold bar prices"""
    try:
        url = "https://www.uobgroup.com/wsm/gold-silver"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        # Try to parse as JSON first
        try:
            data = response.json()
            
            # Extract 1kg cast bar prices
            prices = {}
            for item in data.get('products', []):
                name = item.get('name', '').lower()
                weight = item.get('weight', '').lower()
                
                # Look for 1kg cast bar specifically
                if ('1 kg' in weight or '1kg' in weight) and 'cast' in name:
                    prices['1kg_cast_buy'] = float(item.get('buyPrice', 0))
                    prices['1kg_cast_sell'] = float(item.get('sellPrice', 0))
                    break
            
            if prices:
                return {
                    'success': True,
                    'prices': prices,
                    'source': 'UOB API'
                }
        
        except json.JSONDecodeError:
            # Parse HTML if not JSON
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for price data in HTML
            prices = {}
            # This will need adjustment based on actual HTML structure
            price_rows = soup.find_all('tr')
            for row in price_rows:
                text = row.get_text().lower()
                if '1 kg' in text and 'cast' in text:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        try:
                            buy_text = cells[-2].get_text().strip()
                            sell_text = cells[-1].get_text().strip()
                            prices['1kg_cast_buy'] = float(re.sub(r'[^\d.]', '', buy_text))
                            prices['1kg_cast_sell'] = float(re.sub(r'[^\d.]', '', sell_text))
                        except (ValueError, IndexError):
                            pass
            
            if prices:
                return {
                    'success': True,
                    'prices': prices,
                    'source': 'UOB HTML'
                }
        
        return {
            'success': False,
            'error': 'No 1kg cast bar found',
            'prices': {}
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'prices': {}
        }

def fetch_tradingview_gold():
    """Fetch XAUUSD spot price from TradingView"""
    try:
        url = "https://www.tradingview.com/symbols/XAUUSD/"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # TradingView often has price in meta tags or specific divs
        # Look for the last price
        price_elem = soup.find('span', {'class': re.compile(r'last.*price', re.I)})
        if not price_elem:
            # Try alternative selectors
            price_elem = soup.find('div', {'data-symbol-last': True})
        
        if price_elem:
            price_text = price_elem.get_text().strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            return {
                'success': True,
                'price': price,
                'source': 'TradingView'
            }
        
        return {
            'success': False,
            'error': 'Price element not found',
            'price': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'price': 0
        }

def fetch_cnbc_gold():
    """Fetch XAUUSD spot price from CNBC"""
    try:
        url = "https://www.cnbc.com/quotes/XAU="
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # CNBC typically has price in a specific class
        price_elem = soup.find('span', {'class': re.compile(r'QuoteStrip.*last', re.I)})
        if not price_elem:
            # Alternative selectors
            price_elem = soup.find('span', {'class': 'QuoteStrip-lastPrice'})
        if not price_elem:
            price_elem = soup.find('div', {'class': re.compile(r'.*last.*price', re.I)})
        
        if price_elem:
            price_text = price_elem.get_text().strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            return {
                'success': True,
                'price': price,
                'source': 'CNBC'
            }
        
        return {
            'success': False,
            'error': 'Price element not found',
            'price': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'price': 0
        }

def fetch_cnbc_usdsgd():
    """Fetch USD/SGD from CNBC"""
    try:
        url = "https://www.cnbc.com/quotes/sgd=x"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        price_elem = soup.find('span', {'class': re.compile(r'QuoteStrip.*last', re.I)})
        if not price_elem:
            price_elem = soup.find('span', {'class': 'QuoteStrip-lastPrice'})
        
        if price_elem:
            price_text = price_elem.get_text().strip()
            rate = float(re.sub(r'[^\d.]', '', price_text))
            
            return {
                'success': True,
                'rate': rate,
                'source': 'CNBC'
            }
        
        return {
            'success': False,
            'error': 'Rate element not found',
            'rate': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'rate': 0
        }

def fetch_yahoo_usdsgd():
    """Fetch USD/SGD from Yahoo Finance"""
    try:
        url = "https://finance.yahoo.com/quote/SGD%3DX/"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Yahoo Finance price selector
        price_elem = soup.find('fin-streamer', {'data-symbol': 'SGD=X', 'data-field': 'regularMarketPrice'})
        if not price_elem:
            # Alternative selector
            price_elem = soup.find('span', {'data-reactid': re.compile(r'\d+')})
            if price_elem and 'SGD' not in price_elem.get_text():
                price_elem = None
        
        if price_elem:
            price_text = price_elem.get_text().strip()
            rate = float(re.sub(r'[^\d.]', '', price_text))
            
            return {
                'success': True,
                'rate': rate,
                'source': 'Yahoo Finance'
            }
        
        return {
            'success': False,
            'error': 'Rate element not found',
            'rate': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'rate': 0
        }


def main():
    """Main function to fetch all data and save to JSON"""
    print("=" * 60)
    print("FETCHING GOLD PRICES FROM MULTIPLE SOURCES")
    print("=" * 60)
    
    # Fetch UOB prices
    print("\n[1/5] Fetching UOB 1kg cast bar prices...")
    uob_data = fetch_uob_prices()
    if uob_data['success']:
        print(f"✓ UOB: Success ({uob_data.get('source', 'unknown')})")
    else:
        print(f"✗ UOB: Failed - {uob_data.get('error', 'unknown')}")
    
    # Fetch gold spot from TradingView
    print("\n[2/5] Fetching XAUUSD from TradingView...")
    tv_gold = fetch_tradingview_gold()
    if tv_gold['success']:
        print(f"✓ TradingView: ${tv_gold['price']:.2f}/oz")
    else:
        print(f"✗ TradingView: Failed - {tv_gold.get('error', 'unknown')}")
    
    # Fetch gold spot from CNBC
    print("\n[3/5] Fetching XAUUSD from CNBC...")
    cnbc_gold = fetch_cnbc_gold()
    if cnbc_gold['success']:
        print(f"✓ CNBC Gold: ${cnbc_gold['price']:.2f}/oz")
    else:
        print(f"✗ CNBC Gold: Failed - {cnbc_gold.get('error', 'unknown')}")
    
    # Fetch USD/SGD from CNBC
    print("\n[4/5] Fetching USD/SGD from CNBC...")
    cnbc_forex = fetch_cnbc_usdsgd()
    if cnbc_forex['success']:
        print(f"✓ CNBC Forex: {cnbc_forex['rate']:.4f}")
    else:
        print(f"✗ CNBC Forex: Failed - {cnbc_forex.get('error', 'unknown')}")
    
    # Fetch USD/SGD from Yahoo Finance
    print("\n[5/5] Fetching USD/SGD from Yahoo Finance...")
    yahoo_forex = fetch_yahoo_usdsgd()
    if yahoo_forex['success']:
        print(f"✓ Yahoo Finance: {yahoo_forex['rate']:.4f}")
    else:
        print(f"✗ Yahoo Finance: Failed - {yahoo_forex.get('error', 'unknown')}")
    
    print("\n" + "=" * 60)
    print("AGGREGATING DATA")
    print("=" * 60)
    
    # Average gold spot prices from successful sources
    gold_prices = []
    gold_sources = []
    
    if tv_gold['success']:
        gold_prices.append(tv_gold['price'])
        gold_sources.append('TradingView')
    
    if cnbc_gold['success']:
        gold_prices.append(cnbc_gold['price'])
        gold_sources.append('CNBC')
    
    avg_gold_spot = sum(gold_prices) / len(gold_prices) if gold_prices else 0
    
    # Average USD/SGD rates from successful sources
    forex_rates = []
    forex_sources = []
    
    if cnbc_forex['success']:
        forex_rates.append(cnbc_forex['rate'])
        forex_sources.append('CNBC')
    
    if yahoo_forex['success']:
        forex_rates.append(yahoo_forex['rate'])
        forex_sources.append('Yahoo')
    
    avg_usd_sgd = sum(forex_rates) / len(forex_rates) if forex_rates else 0
    
    # Build result
    result = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'uob_prices_sgd': uob_data.get('prices', {}),
        'gold_spot_usd_per_oz': {
            'average': round(avg_gold_spot, 2),
            'sources': {
                'tradingview': tv_gold.get('price', 0) if tv_gold['success'] else None,
                'cnbc': cnbc_gold.get('price', 0) if cnbc_gold['success'] else None
            },
            'source_count': len(gold_prices),
            'source_names': gold_sources
        },
        'usd_sgd_rate': {
            'average': round(avg_usd_sgd, 4),
            'sources': {
                'cnbc': cnbc_forex.get('rate', 0) if cnbc_forex['success'] else None,
                'yahoo': yahoo_forex.get('rate', 0) if yahoo_forex['success'] else None
            },
            'source_count': len(forex_rates),
            'source_names': forex_sources
        },
        'status': {
            'uob_success': uob_data.get('success', False),
            'gold_spot_success': len(gold_prices) > 0,
            'forex_success': len(forex_rates) > 0,
            'all_sources_success': all([
                uob_data.get('success', False),
                tv_gold.get('success', False),
                cnbc_gold.get('success', False),
                cnbc_forex.get('success', False),
                yahoo_forex.get('success', False)
            ])
        },
        'errors': {
            'uob': uob_data.get('error', None),
            'tradingview_gold': tv_gold.get('error', None),
            'cnbc_gold': cnbc_gold.get('error', None),
            'cnbc_forex': cnbc_forex.get('error', None),
            'yahoo_forex': yahoo_forex.get('error', None)
        }
    }
    
    # Calculate derived values if we have spot and forex data
    if avg_gold_spot > 0 and avg_usd_sgd > 0:
        # 1 troy oz = 31.1035 grams
        sgd_per_gram = (avg_gold_spot * avg_usd_sgd) / 31.1035
        
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
            
            # Spread between buy and sell
            if uob_data['prices'].get('1kg_cast_sell'):
                spread = uob_data['prices']['1kg_cast_buy'] - uob_data['prices']['1kg_cast_sell']
                spread_pct = (spread / uob_data['prices']['1kg_cast_buy']) * 100
                result['calculated']['uob_spread_sgd'] = round(spread, 2)
                result['calculated']['uob_spread_percent'] = round(spread_pct, 2)
    
    # Save to file
    with open('gold_prices.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print("\n✓ Data saved to gold_prices.json")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if avg_gold_spot > 0:
        print(f"\nGold Spot (averaged from {len(gold_prices)} sources):")
        print(f"  ${avg_gold_spot:.2f}/oz USD")
        if tv_gold['success']:
            print(f"  - TradingView: ${tv_gold['price']:.2f}")
        if cnbc_gold['success']:
            print(f"  - CNBC: ${cnbc_gold['price']:.2f}")
    
    if avg_usd_sgd > 0:
        print(f"\nUSD/SGD Rate (averaged from {len(forex_rates)} sources):")
        print(f"  {avg_usd_sgd:.4f}")
        if cnbc_forex['success']:
            print(f"  - CNBC: {cnbc_forex['rate']:.4f}")
        if yahoo_forex['success']:
            print(f"  - Yahoo: {yahoo_forex['rate']:.4f}")
    
    if result.get('calculated'):
        print(f"\nCalculated Spot Prices:")
        print(f"  ${result['calculated']['spot_price_sgd_per_gram']:.2f}/gram SGD")
        print(f"  ${result['calculated']['spot_price_sgd_per_kg']:,.2f}/kg SGD")
    
    if uob_data.get('prices', {}).get('1kg_cast_buy'):
        print(f"\nUOB 1kg Cast Bar:")
        print(f"  Buy:  ${uob_data['prices']['1kg_cast_buy']:,.2f} SGD")
        if uob_data['prices'].get('1kg_cast_sell'):
            print(f"  Sell: ${uob_data['prices']['1kg_cast_sell']:,.2f} SGD")
        
        if result.get('calculated', {}).get('uob_1kg_premium_sgd'):
            print(f"  Premium: ${result['calculated']['uob_1kg_premium_sgd']:,.2f} ({result['calculated']['uob_1kg_premium_percent']:.2f}%)")
        
        if result.get('calculated', {}).get('uob_spread_sgd'):
            print(f"  Spread: ${result['calculated']['uob_spread_sgd']:,.2f} ({result['calculated']['uob_spread_percent']:.2f}%)")
    
    print("\n" + "=" * 60)
    
    # Exit with warning if critical sources failed
    critical_failed = not uob_data['success'] or len(gold_prices) == 0 or len(forex_rates) == 0
    
    if critical_failed:
        print("⚠ WARNING: Some critical data sources failed")
        sys.exit(1)
    else:
        print("✓ All critical data fetched successfully")

if __name__ == '__main__':
    main()
