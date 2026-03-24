import json

from config import API_KEY, BASE_URL
from helpers import log, format_url


def fetch_data(endpoint):
    url = format_url(BASE_URL, endpoint)
    log(f"Fetching from {url} with key={API_KEY[:4]}...")
    return {"status": "ok", "url": url}


def process(data):
    log(f"Processing: {data}")
    return {k: v.upper() if isinstance(v, str) else v for k, v in data.items()}
