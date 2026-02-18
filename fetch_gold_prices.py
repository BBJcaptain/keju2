def fetch_uob_prices():
    import requests

    response = requests.get('https://uob-api-endpoint')
    data = response.json()

    prices = {}

    for item in data['types']:
        if item['description'] == '1kg cast bar':
            prices['1kg_cast_bar'] = {
                'unit': item['unit'],
                'bankBuy': item['bankBuy'],
                'bankSell': item['bankSell']
            }
        elif item['description'] == '100g argor':
            prices['100g_argor'] = {
                'unit': item['unit'],
                'bankBuy': item['bankBuy'],
                'bankSell': item['bankSell']
            }

    return prices