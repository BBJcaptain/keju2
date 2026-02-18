def fetch_uob_prices():
    import requests
    import json

    url = 'https://api.example.com/prices'
    response = requests.get(url)
    data = response.json()

    prices = {}

    for item in data.get('types', []):
        description = item.get('description')
        if description in ['ACB', 'CTB']:
            prices[description] = {
                'buy': item.get('bankBuy'),
                'sell': item.get('bankSell')
            }

    return prices
