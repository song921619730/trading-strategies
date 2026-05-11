#!/usr/bin/env python3
"""Search Tavily proxy for news."""
import requests
import json
import sys

queries = [
    "A股 AI芯片 寒武纪 芯原 凌云光 最新消息 2026年5月",
    "锂电池 丰元股份 永杉锂业 最新动态 2026年5月",
    "新能源车 众泰汽车 浙江荣泰 最新消息 2026年5月"
]

for i, query in enumerate(queries):
    print(f"\n{'='*60}")
    print(f"SEARCH {i+1}: {query}")
    print(f"{'='*60}")
    try:
        r = requests.post(
            "http://localhost:8787/api/search",
            json={"query": query, "max_results": 3},
            timeout=15
        )
        data = r.json()
        results = data.get('results', [])
        if not results:
            # Try alternative field
            results = data.get('output', [])
        if isinstance(results, list) and len(results) > 0:
            for idx, item in enumerate(results):
                title = item.get('title', 'N/A')
                url = item.get('url', 'N/A')
                content = item.get('content', '')[:400]
                print(f"\n--- Result {idx+1} ---")
                print(f"TITLE: {title}")
                print(f"URL: {url}")
                print(f"CONTENT: {content}")
        else:
            print(f"No results found. Raw response (first 500 chars):")
            print(json.dumps(data, ensure_ascii=False)[:500])
    except Exception as e:
        print(f"Error: {e}")
