"""
Pure AI CIO Strategy - News Fetcher
Magic Number: 234003

Purpose: Fetch news using web search for market analysis.
Usage: python fetch_news.py "search query" [count]
"""
import sys
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote
import ssl

CST = timezone(timedelta(hours=8))


def fetch_news_tavily(query: str, count: int = 15):
    """Try fetching news via Tavily API if available."""
    try:
        # Check if we have a Tavily API key in environment
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return None

        url = "https://api.tavily.com/search"
        data = json.dumps({
            "api_key": api_key,
            "query": query,
            "max_results": count,
            "search_depth": "basic",
            "include_answer": False,
        }).encode()

        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        response = urlopen(req, context=ctx, timeout=15)
        result = json.loads(response.read().decode())

        news = []
        for item in result.get("results", [])[:count]:
            news.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:200],
                "source": item.get("source", ""),
                "query": query,
            })
        return news
    except Exception:
        return None


def fetch_news_via_search(query: str, count: int = 15):
    """Fallback: use public RSS or basic search."""
    news = []
    try:
        # Try Google News RSS as fallback
        encoded = quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        req = Request(rss_url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        ctx = ssl.create_default_context()
        response = urlopen(req, context=ctx, timeout=10)
        content = response.read().decode('utf-8', errors='replace')

        import xml.etree.ElementTree as ET
        root = ET.fromstring(content)

        for item in root.findall('.//item')[:count]:
            title_elem = item.find('title')
            link_elem = item.find('link')
            source_elem = item.find('source')
            news.append({
                "title": title_elem.text if title_elem is not None else "",
                "url": link_elem.text if link_elem is not None else "",
                "snippet": "",
                "source": source_elem.text if source_elem is not None else "Google News",
                "query": query,
            })
    except Exception:
        pass

    return news if news else None


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_news.py <query> [count]"}))
        return

    query = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    # Try Tavily first, then fallback
    news = fetch_news_tavily(query, count)
    if news is None:
        news = fetch_news_via_search(query, count)

    if news is None or len(news) == 0:
        result = {"status": "ERROR", "news": [], "query": query, "count": 0}
    else:
        result = {"status": "OK", "news": news, "query": query, "count": len(news)}

    # Save to logs/news/
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "news")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M")
    filename = f"{timestamp}_{query.replace(' ', '_')[:40]}.json"
    filepath = os.path.join(logs_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
