#!/usr/bin/env python3
"""
Fetch UOB gold prices, spot gold price, and USD/SGD exchange rate
Runs every 10 minutes via GitHub Actions

Sources:
1. UOB cast 1kg bar prices
2. CNBC XAUUSD spot (web scraping)
3. Metals.live XAUUSD spot (JSON API)
4. GoldPrice.org XAUUSD spot (JSON API)
5. CNBC USD/SGD (web scraping)
6. ExchangeRate-API USD/SGD (JSON API)
7. Frankfurter USD/SGD (JSON API, ECB data)
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

        data = response.json()

        # Try multiple possible response structures
        product_lists = []

        # Structure 1: {products: [...]}
        if isinstance(data.get('products'), list):
            product_lists.append(data['products'])

        # Structure 2: {goldProducts: [...]}
        if isinstance(data.get('goldProducts'), list):
            product_lists.append(data['goldProducts'])

        # Structure 3: top-level array
        if isinstance(data, list):
            product_lists.append(data)

        # Structure 4: nested under any key containing 'gold' or 'product'
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and any(k in key.lower() for k in ['gold', 'product', 'item', 'price']):
                    if val not in product_lists:
                        product_lists.append(val)

        prices = {}
        for items in product_lists:
            for item in items:
                if not isinstance(item, dict):
                    continue

                # Combine all text fields for matching
                all_text = ' '.join(str(v).lower() for v in item.values() if isinstance(v, (str, int, float)))

                is_1kg = any(t in all_text for t in ['1 kg', '1kg', '1000g', '1000 g'])
                is_bar = any(t in all_text for t in ['cast', 'bar'])

                if is_1kg and is_bar:
                    # Try multiple field name patterns for buy/sell prices
                    buy_keys = ['buyPrice', 'buyingPrice', 'buy_price', 'sellingPrice', 'selling_price', 'buy']
                    sell_keys = ['sellPrice', 'sellingPrice', 'sell_price', 'buyingPrice', 'buying_price', 'sell']

                    # UOB terminology: "selling price" = price UOB sells to you (you buy)
                    # "buying price" = price UOB buys from you (you sell)
                    for key in buy_keys:
                        if key in item and float(item[key]) > 0:
                            prices['1kg_cast_buy'] = float(item[key])
                            break
                    for key in sell_keys:
                        if key in item and float(item[key]) > 0:
                            prices['1kg_cast_sell'] = float(item[key])
                            break

                    item_name = item.get('name', item.get('productName', 'unknown'))
                    print(f"  Found: {item_name}")
                    break

                # Fallback: just get any 1kg product
                if is_1kg and not prices:
                    for key in ['buyPrice', 'buyingPrice', 'sellingPrice', 'buy_price', 'buy']:
                        if key in item and float(item.get(key, 0)) > 0:
                            prices['1kg_cast_buy'] = float(item[key])
                            break
                    for key in ['sellPrice', 'sellingPrice', 'buyingPrice', 'sell_price', 'sell']:
                        if key in item and float(item.get(key, 0)) > 0:
                            prices['1kg_cast_sell'] = float(item[key])
                            break

        if prices:
            return {
                'success': True,
                'prices': prices,
                'source': 'UOB'
            }

        return {
            'success': False,
            'error': 'No 1kg bar found in response',
            'prices': {}
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'prices': {}
        }

def fetch_metals_live_gold():
    """Fetch XAUUSD spot price from Metals.live API (free, no key)"""
    try:
        url = "https://api.metals.live/v1/spot"

        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Response is a JSON array: [{"gold": 2650.50}, {"silver": 31.25}, ...]
        price = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'gold' in item:
                    price = float(item['gold'])
                    break

        if price and 1000 < price < 10000:
            return {
                'success': True,
                'price': price,
                'source': 'Metals.live'
            }

        return {
            'success': False,
            'error': 'Gold price not found in response',
            'price': 0
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'price': 0
        }

def fetch_goldprice_org():
    """Fetch XAUUSD spot price from GoldPrice.org API (free, no key)"""
    try:
        url = "https://data-asg.goldprice.org/dbXRates/USD"

        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Response: {items: [{curr: "USD", xauPrice: 2650.50, ...}]}
        price = float(data.get('items', [{}])[0].get('xauPrice', 0))

        if price and 1000 < price < 10000:
            return {
                'success': True,
                'price': price,
                'source': 'GoldPrice.org'
            }

        return {
            'success': False,
            'error': f'Price out of range or missing: {price}',
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
                        if 1000 < test_price < 10000:
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
                        if 1000 < test_price < 10000:
                            price = test_price
                    except:
                        pass
        
        if price and 1000 < price < 10000:
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

def fetch_exchangerate_api_usdsgd():
    """Fetch USD/SGD from ExchangeRate-API (free, no key)"""
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
                    'source': 'ExchangeRate-API'
                }

        return {
            'success': False,
            'error': 'Rate not found or out of range',
            'rate': 0
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'rate': 0
        }

def fetch_frankfurter_usdsgd():
    """Fetch USD/SGD from Frankfurter API (free, no key, ECB data)"""
    try:
        url = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=SGD"

        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Response: {amount: 1.0, base: "USD", date: "...", rates: {SGD: 1.34}}
        rate = float(data.get('rates', {}).get('SGD', 0))

        if 1.0 < rate < 2.0:
            return {
                'success': True,
                'rate': rate,
                'source': 'Frankfurter'
            }

        return {
            'success': False,
            'error': f'Rate out of range or missing: {rate}',
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

    # Fetch gold spot from CNBC (web scraping)
    print("\n[2/7] Fetching XAUUSD from CNBC...")
    cnbc_gold = fetch_cnbc_gold()
    if cnbc_gold['success']:
        print(f"✓ CNBC Gold: ${cnbc_gold['price']:.2f}/oz")
    else:
        print(f"✗ CNBC Gold: Failed - {cnbc_gold.get('error', 'unknown')}")

    # Fetch gold spot from Metals.live (JSON API)
    print("\n[3/7] Fetching XAUUSD from Metals.live...")
    metals_gold = fetch_metals_live_gold()
    if metals_gold['success']:
        print(f"✓ Metals.live Gold: ${metals_gold['price']:.2f}/oz")
    else:
        print(f"✗ Metals.live Gold: Failed - {metals_gold.get('error', 'unknown')}")

    # Fetch gold spot from GoldPrice.org (JSON API)
    print("\n[4/7] Fetching XAUUSD from GoldPrice.org...")
    goldprice_gold = fetch_goldprice_org()
    if goldprice_gold['success']:
        print(f"✓ GoldPrice.org Gold: ${goldprice_gold['price']:.2f}/oz")
    else:
        print(f"✗ GoldPrice.org Gold: Failed - {goldprice_gold.get('error', 'unknown')}")

    # Fetch USD/SGD from CNBC (web scraping)
    print("\n[5/7] Fetching USD/SGD from CNBC...")
    cnbc_forex = fetch_cnbc_usdsgd()
    if cnbc_forex['success']:
        print(f"✓ CNBC Forex: {cnbc_forex['rate']:.4f}")
    else:
        print(f"✗ CNBC Forex: Failed - {cnbc_forex.get('error', 'unknown')}")

    # Fetch USD/SGD from ExchangeRate-API (JSON API)
    print("\n[6/7] Fetching USD/SGD from ExchangeRate-API...")
    er_forex = fetch_exchangerate_api_usdsgd()
    if er_forex['success']:
        print(f"✓ ExchangeRate-API: {er_forex['rate']:.4f}")
    else:
        print(f"✗ ExchangeRate-API: Failed - {er_forex.get('error', 'unknown')}")

    # Fetch USD/SGD from Frankfurter (JSON API)
    print("\n[7/7] Fetching USD/SGD from Frankfurter...")
    frank_forex = fetch_frankfurter_usdsgd()
    if frank_forex['success']:
        print(f"✓ Frankfurter: {frank_forex['rate']:.4f}")
    else:
        print(f"✗ Frankfurter: Failed - {frank_forex.get('error', 'unknown')}")
    
    print("\n" + "=" * 60)
    print("AGGREGATING DATA WITH CROSS-VALIDATION")
    print("=" * 60)
    
    # Collect all gold prices
    all_gold_prices = []
    all_gold_data = []

    for source_data in [cnbc_gold, metals_gold, goldprice_gold]:
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

    for fx_data in [cnbc_forex, er_forex, frank_forex]:
        if fx_data.get('success'):
            forex_rates.append(fx_data['rate'])
            forex_sources.append(fx_data['source'])
    
    avg_usd_sgd = sum(forex_rates) / len(forex_rates) if forex_rates else 0
    
    # Build result
    result = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'uob_prices_sgd': uob_data.get('prices', {}),
        'gold_spot_usd_per_oz': {
            'average': round(avg_gold_spot, 2),
            'sources': {
                'cnbc': cnbc_gold.get('price', 0) if cnbc_gold['success'] else None,
                'metals_live': metals_gold.get('price', 0) if metals_gold['success'] else None,
                'goldprice_org': goldprice_gold.get('price', 0) if goldprice_gold['success'] else None
            },
            'source_count': len(gold_prices),
            'source_names': gold_sources,
            'cross_validated': len(all_gold_prices) >= 3
        },
        'usd_sgd_rate': {
            'average': round(avg_usd_sgd, 4),
            'sources': {
                'cnbc': cnbc_forex.get('rate', 0) if cnbc_forex['success'] else None,
                'exchangerate_api': er_forex.get('rate', 0) if er_forex['success'] else None,
                'frankfurter': frank_forex.get('rate', 0) if frank_forex['success'] else None
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
                cnbc_gold.get('success', False),
                metals_gold.get('success', False),
                goldprice_gold.get('success', False),
                cnbc_forex.get('success', False),
                er_forex.get('success', False),
                frank_forex.get('success', False)
            ])
        },
        'errors': {
            'uob': uob_data.get('error', None),
            'cnbc_gold': cnbc_gold.get('error', None),
            'metals_live_gold': metals_gold.get('error', None),
            'goldprice_org_gold': goldprice_gold.get('error', None),
            'cnbc_forex': cnbc_forex.get('error', None),
            'exchangerate_api_forex': er_forex.get('error', None),
            'frankfurter_forex': frank_forex.get('error', None)
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
        for fx_data in [cnbc_forex, er_forex, frank_forex]:
            if fx_data.get('success'):
                print(f"  - {fx_data['source']}: {fx_data['rate']:.4f}")
    
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
