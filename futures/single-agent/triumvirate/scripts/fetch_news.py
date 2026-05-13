"""
Triumvirate — 新闻采集 (后备方案)

职责: 当 Cron 的 web_search 工具不可用时通过 Tavily API 获取新闻
日志: 每次扫描记录到 logs/news/

注意:
- 主方案是 Cron 直接使用 web_search 工具 (Tavily MCP)
- 此脚本仅作为后备方案，通过 subprocess 调用
"""
import sys
import os
import json
import urllib.request
import urllib.parse
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)


def log_result(result: dict, query: str):
    """Save result to logs/news/"""
    logs_dir = os.path.join(TRIUMVIRATE_DIR, "logs", "news")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M")
    # Sanitize query for filename
    safe_query = query.replace(' ', '_')[:40]
    safe_query = ''.join(c for c in safe_query if c.isalnum() or c in '_-')
    filepath = os.path.join(logs_dir, f"{timestamp}_{safe_query}.json")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def search_via_tavily_api(query: str, count: int = 10):
    """Try Tavily API (Docker MCP endpoint)."""
    try:
        url = "http://localhost:8787/mcp/"
        data = json.dumps({
            "query": query,
            "max_results": count,
        }).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        response = urllib.request.urlopen(req, context=ctx, timeout=15)
        result = json.loads(response.read().decode())
        return result
    except Exception:
        return None


def search_via_google_rss(query: str, count: int = 10):
    """Fallback: Google News RSS."""
    news = []
    try:
        encoded = urllib.parse.quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(rss_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        ctx = ssl.create_default_context()
        response = urllib.request.urlopen(req, context=ctx, timeout=10)
        content = response.read().decode('utf-8', errors='replace')

        root = ET.fromstring(content)
        for item in root.findall('.//item')[:count]:
            title = item.find('title')
            link = item.find('link')
            source = item.find('source')
            news.append({
                "title": title.text if title is not None else "",
                "url": link.text if link is not None else "",
                "snippet": "",
                "source": source.text if source is not None else "Google News",
                "query": query,
            })
    except Exception:
        pass
    return news if news else None


def main():
    if len(sys.argv) < 2:
        output = {"status": "ERROR", "news": [], "query": "", "count": 0}
        print(json.dumps(output))
        return

    query = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    # Try Tavily Docker endpoint first
    result = search_via_tavily_api(query, count)
    if result and result.get("results"):
        news = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:200],
                "source": item.get("source", ""),
                "query": query,
            }
            for item in result["results"][:count]
        ]
        output = {"status": "OK", "news": news, "query": query, "count": len(news)}
    else:
        # Fallback to Google RSS
        news = search_via_google_rss(query, count)
        if news:
            output = {"status": "OK", "news": news, "query": query, "count": len(news)}
        else:
            output = {"status": "ERROR", "news": [], "query": query, "count": 0}

    log_result(output, query)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
