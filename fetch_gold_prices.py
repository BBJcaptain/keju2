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
        
        # Parse as JSON
        data = response.json()
        
        # Extract 1kg cast bar prices - be flexible with naming
        prices = {}
        for item in data.get('products', []):
            name = str(item.get('name', '')).lower()
            weight = str(item.get('weight', '')).lower()
            product_type = str(item.get('type', '')).lower()
            
            # Look for 1kg AND cast (or casted, casting, etc.)
            is_1kg = '1 kg' in weight or '1kg' in weight or '1000g' in weight
            is_cast = 'cast' in name or 'cast' in product_type or 'bar' in name
            
            if is_1kg and (is_cast or 'bar' in name):
                prices['1kg_cast_buy'] = float(item.get('buyPrice', 0))
                prices['1kg_cast_sell'] = float(item.get('sellPrice', 0))
                print(f"  Found: {item.get('name', 'unknown')}")
                break
            
            # Fallback: just get any 1kg if cast not found
            if is_1kg and not prices:
                prices['1kg_cast_buy'] = float(item.get('buyPrice', 0))
                prices['1kg_cast_sell'] = float(item.get('sellPrice', 0))
        
        if prices:
            return {
                'success': True,
                'prices': prices,
                'source': 'UOB'
            }
        
        return {
            'success': False,
            'error': 'No 1kg bar found in products list',
            'prices': {}
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'prices': {}
        }

def fetch_fallback_gold():
    """Fetch gold price from reliable API fallback"""
    try:
        # Using metals-api.com free endpoint
        url = "https://api.metals.live/v1/spot/gold"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Price is typically in data
        price = float(data.get('price', 0))
        
        if 1000 < price < 8000:
            return {
                'success': True,
                'price': price,
                'source': 'Metals.live'
            }
        
        return {
            'success': False,
            'error': 'Price out of range',
            'price': 0
        }
    
    except Exception as e:
        # Try alternative: goldprice.org
        try:
            url2 = "https://data-asg.goldprice.org/dbXRates/USD"
            response2 = requests.get(url2, timeout=10)
            response2.raise_for_status()
            data2 = response2.json()
            
            price = float(data2.get('items', [{}])[0].get('xauPrice', 0))
            
            if 1000 < price < 8000:
                return {
                    'success': True,
                    'price': price,
                    'source': 'GoldPrice.org'
                }
        except:
            pass
        
        return {
            'success': False,
            'error': str(e),
            'price': 0
        }

def fetch_kitco_gold():
    """Fetch XAUUSD from Kitco"""
    try:
        url = "https://www.kitco.com/market/gold"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for gold price - Kitco has various selectors
        price = None
        
        # Try to find bid price
        for elem in soup.find_all(['span', 'div'], {'class': True}):
            text = elem.get_text().strip()
            classes = ' '.join(elem.get('class', [])).lower()
            
            if ('bid' in classes or 'price' in classes) and '$' in text:
                try:
                    # Extract number
                    match = re.search(r'\$?([\d,]+\.?\d*)', text)
                    if match:
                        test_price = float(match.group(1).replace(',', ''))
                        if 1000 < test_price < 8000:
                            price = test_price
                            break
                except:
                    pass
        
        if price:
            return {
                'success': True,
                'price': price,
                'source': 'Kitco'
            }
        
        return {
            'success': False,
            'error': 'Price not found',
            'price': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'price': 0
        }

def fetch_investing_gold():
    """Fetch XAUUSD from Investing.com"""
    try:
        url = "https://www.investing.com/currencies/xau-usd"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        price = None
        
        # Investing.com uses various selectors
        price_elem = soup.find('span', {'data-test': 'instrument-price-last'})
        if price_elem:
            try:
                price_text = price_elem.get_text().strip()
                price = float(re.sub(r'[^\d.]', '', price_text))
            except:
                pass
        
        # Alternative selector
        if not price:
            for elem in soup.find_all('span', {'class': True}):
                classes = ' '.join(elem.get('class', [])).lower()
                if 'last' in classes or 'price' in classes:
                    try:
                        text = elem.get_text().strip()
                        test_price = float(re.sub(r'[^\d.]', '', text))
                        if 1000 < test_price < 8000:
                            price = test_price
                            break
                    except:
                        pass
        
        if price and 1000 < price < 8000:
            return {
                'success': True,
                'price': price,
                'source': 'Investing.com'
            }
        
        return {
            'success': False,
            'error': 'Price not found',
            'price': 0
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'price': 0
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
        
        # Try multiple selectors
        price = None
        
        # Method 1: Look for QuoteStrip-lastPrice
        price_elem = soup.find('span', {'class': 'QuoteStrip-lastPrice'})
        if price_elem:
            try:
                price_text = price_elem.get_text().strip()
                price = float(re.sub(r'[^\d.]', '', price_text))
            except:
                pass
        
        # Method 2: Look for any element with "last" and "price" in class
        if not price:
            for elem in soup.find_all('span', {'class': True}):
                classes = ' '.join(elem.get('class', [])).lower()
                if 'last' in classes and 'price' in classes:
                    try:
                        price_text = elem.get_text().strip()
                        test_price = float(re.sub(r'[^\d.]', '', price_text))
                        # Sanity check: gold should be $1000-$8000/oz
                        if 1000 < test_price < 8000:
                            price = test_price
                            break
                    except:
                        pass
        
        # Method 3: Look in meta tags
        if not price:
            meta = soup.find('meta', {'property': 'og:description'})
            if meta:
                content = meta.get('content', '')
                # Extract price from description
                match = re.search(r'\$?([\d,]+\.?\d*)', content)
                if match:
                    try:
                        test_price = float(match.group(1).replace(',', ''))
                        if 1000 < test_price < 8000:
                            price = test_price
                    except:
                        pass
        
        if price and 1000 < price < 8000:
            return {
                'success': True,
                'price': price,
                'source': 'CNBC'
            }
        
        return {
            'success': False,
            'error': f'Price not found or out of range: {price}',
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
    print("\n[1/7] Fetching UOB 1kg cast bar prices...")
    uob_data = fetch_uob_prices()
    if uob_data['success']:
        print(f"✓ UOB: Success ({uob_data.get('source', 'unknown')})")
    else:
        print(f"✗ UOB: Failed - {uob_data.get('error', 'unknown')}")
    
    # Fetch gold spot from TradingView
    print("\n[2/7] Fetching XAUUSD from TradingView...")
    tv_gold = fetch_tradingview_gold()
    if tv_gold['success']:
        print(f"✓ TradingView: ${tv_gold['price']:.2f}/oz")
    else:
        print(f"✗ TradingView: Failed - {tv_gold.get('error', 'unknown')}")
    
    # Fetch gold spot from CNBC
    print("\n[3/7] Fetching XAUUSD from CNBC...")
    cnbc_gold = fetch_cnbc_gold()
    if cnbc_gold['success']:
        print(f"✓ CNBC Gold: ${cnbc_gold['price']:.2f}/oz")
    else:
        print(f"✗ CNBC Gold: Failed - {cnbc_gold.get('error', 'unknown')}")
    
    # Fetch gold spot from Kitco
    print("\n[4/7] Fetching XAUUSD from Kitco...")
    kitco_gold = fetch_kitco_gold()
    if kitco_gold['success']:
        print(f"✓ Kitco Gold: ${kitco_gold['price']:.2f}/oz")
    else:
        print(f"✗ Kitco Gold: Failed - {kitco_gold.get('error', 'unknown')}")
    
    # Fetch gold spot from Investing.com
    print("\n[5/7] Fetching XAUUSD from Investing.com...")
    investing_gold = fetch_investing_gold()
    if investing_gold['success']:
        print(f"✓ Investing.com Gold: ${investing_gold['price']:.2f}/oz")
    else:
        print(f"✗ Investing.com Gold: Failed - {investing_gold.get('error', 'unknown')}")
    
    # Fetch USD/SGD from CNBC
    print("\n[6/7] Fetching USD/SGD from CNBC...")
    cnbc_forex = fetch_cnbc_usdsgd()
    if cnbc_forex['success']:
        print(f"✓ CNBC Forex: {cnbc_forex['rate']:.4f}")
    else:
        print(f"✗ CNBC Forex: Failed - {cnbc_forex.get('error', 'unknown')}")
    
    # Fetch USD/SGD from Yahoo Finance
    print("\n[7/7] Fetching USD/SGD from Yahoo Finance...")
    yahoo_forex = fetch_yahoo_usdsgd()
    if yahoo_forex['success']:
        print(f"✓ Yahoo Finance: {yahoo_forex['rate']:.4f}")
    else:
        print(f"✗ Yahoo Finance: Failed - {yahoo_forex.get('error', 'unknown')}")
    
    # If multiple gold sources failed, try fallback API
    fallback_gold = {'success': False, 'price': 0}
    gold_success_count = sum([tv_gold['success'], cnbc_gold['success'], kitco_gold['success'], investing_gold['success']])
    
    if gold_success_count < 2:
        print("\n[FALLBACK] Trying reliable gold price API...")
        fallback_gold = fetch_fallback_gold()
        if fallback_gold['success']:
            print(f"✓ Fallback Gold API: ${fallback_gold['price']:.2f}/oz ({fallback_gold['source']})")
        else:
            print(f"✗ Fallback Gold API: Failed")
    
    print("\n" + "=" * 60)
    print("AGGREGATING DATA WITH CROSS-VALIDATION")
    print("=" * 60)
    
    # Collect all gold prices
    all_gold_prices = []
    all_gold_data = []
    
    for source_data in [tv_gold, cnbc_gold, kitco_gold, investing_gold, fallback_gold]:
        if source_data.get('success'):
            all_gold_prices.append(source_data['price'])
            all_gold_data.append(source_data)
    
    # Cross-validation: remove outliers if we have 3+ sources
    gold_prices = []
    gold_sources = []
    
    if len(all_gold_prices) >= 3:
        # Calculate median
        sorted_prices = sorted(all_gold_prices)
        median_price = sorted_prices[len(sorted_prices) // 2]
        
        # Accept prices within 5% of median
        tolerance = median_price * 0.05
        
        print(f"\nCross-validation (median: ${median_price:.2f}):")
        for data in all_gold_data:
            price = data['price']
            source = data.get('source', 'unknown')
            diff_pct = abs((price - median_price) / median_price) * 100
            
            if abs(price - median_price) <= tolerance:
                gold_prices.append(price)
                gold_sources.append(source)
                print(f"  ✓ {source}: ${price:.2f} (±{diff_pct:.1f}% from median)")
            else:
                print(f"  ✗ {source}: ${price:.2f} (±{diff_pct:.1f}% OUTLIER - excluded)")
    else:
        # Not enough sources for validation, use all
        gold_prices = all_gold_prices
        gold_sources = [d.get('source', 'unknown') for d in all_gold_data]
    
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
                'cnbc': cnbc_gold.get('price', 0) if cnbc_gold['success'] else None,
                'kitco': kitco_gold.get('price', 0) if kitco_gold['success'] else None,
                'investing': investing_gold.get('price', 0) if investing_gold['success'] else None,
                'fallback': fallback_gold.get('price', 0) if fallback_gold.get('success') else None
            },
            'source_count': len(gold_prices),
            'source_names': gold_sources,
            'cross_validated': len(all_gold_prices) >= 3
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
            'gold_sources_count': len(gold_prices),
            'forex_sources_count': len(forex_rates),
            'cross_validated': len(all_gold_prices) >= 3,
            'all_sources_success': all([
                uob_data.get('success', False),
                tv_gold.get('success', False),
                cnbc_gold.get('success', False),
                kitco_gold.get('success', False),
                investing_gold.get('success', False),
                cnbc_forex.get('success', False),
                yahoo_forex.get('success', False)
            ])
        },
        'errors': {
            'uob': uob_data.get('error', None),
            'tradingview_gold': tv_gold.get('error', None),
            'cnbc_gold': cnbc_gold.get('error', None),
            'kitco_gold': kitco_gold.get('error', None),
            'investing_gold': investing_gold.get('error', None),
            'cnbc_forex': cnbc_forex.get('error', None),
            'yahoo_forex': yahoo_forex.get('error', None),
            'fallback_gold': fallback_gold.get('error', None) if fallback_gold.get('success') is not None else None
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
        for source_name in gold_sources:
            # Find the price for this source
            for data in all_gold_data:
                if data.get('source') == source_name:
                    print(f"  - {source_name}: ${data['price']:.2f}")
                    break
    
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
        print("⚠ WARNING: Missing critical data (need UOB + at least 1 gold source + 1 forex source)")
        sys.exit(1)
    else:
        print("✓ All critical data fetched successfully")
        print(f"✓ Gold sources: {len(gold_prices)} (cross-validated: {len(all_gold_prices) >= 3})")
        print(f"✓ Forex sources: {len(forex_rates)}")

if __name__ == '__main__':
    main()
