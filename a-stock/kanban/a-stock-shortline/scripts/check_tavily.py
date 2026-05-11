#!/usr/bin/env python3
"""Check Tavily status and try web search."""
import requests
try:
    r = requests.get('http://localhost:8787/api/status', timeout=5)
    print(f'Status: {r.status_code}')
    print(r.text[:500])
except Exception as e:
    print(f'Error: {e}')
