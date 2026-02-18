# New Implementation of fetch_uob_prices

import requests
from bs4 import BeautifulSoup


def fetch_uob_prices():
    # URL for fetching gold prices
    url = 'https://www.uobgroup.com/wsm/gold-silver'
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception('Failed to fetch data from UOB')

    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract prices for 1kg cast bar and 100g argor
    prices = {}
    prices['1kg_cast_bar'] = soup.find('div', {'id': '1kg_bar'}).text.strip()
    prices['100g_argor'] = soup.find('div', {'id': '100g_argor'}).text.strip()

    return prices
