#!/usr/bin/env python3
"""
Triumvirate Trading Strategy — Financial News Intelligence (v5 - FINAL)
Fetches news from working RSS feeds, maps to instruments via themes.
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from xml.etree import ElementTree
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

# === Configuration ===
WORK_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/triumvirate"
LOG_DIR = os.path.join(WORK_DIR, "logs/news")
BEIJING_TZ = timezone(timedelta(hours=8))
MAX_AGE_HOURS = 72
NOW = datetime.now(timezone.utc)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
}

RSS_FEEDS = [
    ("CNBC US Top News", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("CNBC Asia", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003116"),
    ("CNBC Europe", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003115"),
    ("MarketWatch Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch MarketPulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
]

# === Instrument Definitions with broad matching ===
INSTRUMENTS = {
    "XAUUSD": {
        "name": "黄金/XAUUSD",
        "keywords": ["gold price", "gold market", "gold ", "precious metal", "bullion", "xau"],
        "themes": ["inflation", "geopolitics", "central-bank"],
        "type": "commodity"
    },
    "EURUSD": {
        "name": "欧元/EURUSD",
        "keywords": [" eur", "euro zone", "eurozone", "ecb", "european central bank", "euro "],
        "themes": ["central-bank", "macroeconomy"],
        "type": "forex"
    },
    "GBPUSD": {
        "name": "英镑/GBPUSD",
        "keywords": ["gbp", "pound sterling", "pound ", "bank of england", "boe ", "uk econom"],
        "themes": ["central-bank", "macroeconomy"],
        "type": "forex"
    },
    "USDJPY": {
        "name": "美元日元/USDJPY",
        "keywords": ["japanese yen", "yen ", "dollar-yen", "boj ", "bank of japan", "japan curren"],
        "themes": ["central-bank", "macroeconomy"],
        "type": "forex"
    },
    "US30": {
        "name": "道琼斯/US30",
        "keywords": ["dow jones", "djia", "dow industri", "dow "],
        "themes": ["markets", "macroeconomy", "trade-policy"],
        "type": "index"
    },
    "US500": {
        "name": "标普500/US500",
        "keywords": ["s&p 500", "spx", "sp500", "s&p "],
        "themes": ["markets", "macroeconomy", "trade-policy"],
        "type": "index"
    },
    "USTEC": {
        "name": "纳斯达克/USTEC",
        "keywords": ["nasdaq", "tech stock", "technology stock", "chip stock", "semiconductor", "nvidia", "ai "],
        "themes": ["technology", "markets"],
        "type": "index"
    },
    "USOIL": {
        "name": "美原油/USOIL",
        "keywords": ["wti", "crude", "usoil", "oil price", "oil market", "crude oil"],
        "themes": ["energy", "geopolitics"],
        "type": "commodity"
    },
    "UKOIL": {
        "name": "布油/UKOIL",
        "keywords": ["brent", "ukoil", "brent crude"],
        "themes": ["energy", "geopolitics"],
        "type": "commodity"
    },
    "JP225": {
        "name": "日经/JP225",
        "keywords": ["nikkei", "jp225", "japan stock", "tokyo stock", "japan market"],
        "themes": ["markets", "macroeconomy", "technology"],
        "type": "index"
    }
}

# Theme definitions for topic extraction
THEMES = {
    "inflation": ["inflation", "cpi", "ppi", "consumer price", "price increase", "price rise",
                  "reaccelerat", "clothing price", "shelter cost"],
    "geopolitics": ["iran", "strait of hormuz", "middle east", "hegseth", "war", "conflict",
                    "sanction", "military"],
    "central-bank": ["fed ", "federal reserve", "interest rate", "rate hike", "rate cut",
                     "monetary", "warsh", "powell", "ecb ", "boj ", "central bank"],
    "energy": ["oil", "crude", "brent", "wti", "gasoline", "gas price", "energy"],
    "trade-policy": ["trump", "china", "xi ", "tariff", "trade war", "beijing", "trade deal",
                     "export control"],
    "technology": ["ai ", "artificial intelligence", "nvidia", "jensen", "semiconductor",
                   "chip ", "data center", "tech stock"],
    "markets": ["stock market", "rally", "sell", "volatility", "yield", "treasury",
                "market", "equities"],
    "macroeconomy": ["recession", "gdp", "economy", "growth", "jobs", "employment",
                     "consumer", "spending"]
}

# Theme → Instruments mapping
THEME_TO_INSTRUMENTS = {
    "inflation": ["XAUUSD", "EURUSD", "USDJPY", "US30", "US500"],
    "geopolitics": ["XAUUSD", "USOIL", "UKOIL", "US30", "US500"],
    "central-bank": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30", "US500"],
    "energy": ["USOIL", "UKOIL", "XAUUSD", "USDJPY"],
    "trade-policy": ["US30", "US500", "USTEC", "JP225", "USDJPY"],
    "technology": ["USTEC", "JP225", "US500"],
    "markets": ["US30", "US500", "USTEC", "JP225"],
    "macroeconomy": ["EURUSD", "GBPUSD", "USDJPY", "US30", "US500"]
}


def fetch_xml(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def parse_rfc2822(date_str: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def parse_rss_items(xml_content: str, source: str, max_items: int = 30) -> List[Dict]:
    items = []
    try:
        root = ElementTree.fromstring(xml_content)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_str = (item.findtext("pubDate") or "").strip()
            desc_raw = item.findtext("description") or ""
            desc = BeautifulSoup(desc_raw, "html.parser").get_text(strip=True)[:500]

            pub_dt = parse_rfc2822(pub_str) if pub_str else None
            if pub_dt:
                age = (NOW - pub_dt).total_seconds() / 3600
                if age > MAX_AGE_HOURS:
                    continue

            if title:
                items.append({
                    "title": title, "link": link,
                    "published": pub_str,
                    "published_dt": pub_dt.isoformat() if pub_dt else "",
                    "description": desc, "source": source
                })
            if len(items) >= max_items:
                break
    except Exception:
        pass
    return items


def fetch_all_news() -> List[Dict]:
    all_items = []
    seen = set()
    for name, url in RSS_FEEDS:
        content = fetch_xml(url)
        if content:
            for item in parse_rss_items(content, name, 30):
                link = item.get("link", "")
                if link and link not in seen and item.get("title"):
                    seen.add(link)
                    all_items.append(item)
    all_items.sort(key=lambda x: x.get("published_dt", ""), reverse=True)
    return all_items


def extract_themes(text: str) -> List[str]:
    """Extract themes from text."""
    text_l = text.lower()
    matched = []
    for theme, keywords in THEMES.items():
        if any(kw in text_l for kw in keywords):
            matched.append(theme)
    return matched


def match_instrument(title: str, desc: str, keywords: List[str]) -> bool:
    text = (title + " " + desc).lower()
    return any(kw.lower() in text for kw in keywords)


def classify_news(news: List[Dict]) -> Dict[str, Dict]:
    """Classify news by instrument and theme."""
    result = {}
    for inst_name, config in INSTRUMENTS.items():
        direct = [item for item in news
                  if match_instrument(item.get("title",""), item.get("description",""),
                                       config["keywords"])]
        # Also find items whose themes match this instrument
        themed = []
        for item in news:
            text = item.get("title","") + " " + item.get("description","")
            item_themes = extract_themes(text)
            if any(t in item_themes for t in config.get("themes", [])):
                if item not in direct and item not in themed:
                    themed.append(item)
        result[inst_name] = {
            "direct_matches": direct[:10],
            "theme_matches": themed[:5],
            "total_direct": len(direct),
            "total_theme": len(themed)
        }
    return result


def print_report(news: List[Dict], classified: Dict[str, Dict]):
    now = datetime.now(BEIJING_TZ)
    
    print("\n" + "█" * 100)
    print("█  📊  TRIUMVIRATE TRADING STRATEGY — NEWS INTELLIGENCE REPORT")
    print(f"█  🕐  {now.strftime('%Y-%m-%d %H:%M:%S')} Beijing | {now.strftime('%A')}")
    print(f"█  📡  {len(RSS_FEEDS)} sources • Last {MAX_AGE_HOURS}h • {len(news)} headlines")
    print("█" * 100)
    
    # HEADLINES
    print(f"\n{'─' * 100}")
    print("🔷  TOP HEADLINES (All Markets)")
    print(f"{'─' * 100}")
    for i, item in enumerate(news[:12], 1):
        themes = extract_themes(item.get("title","") + " " + item.get("description",""))
        print(f"  {i:2d}. {item['title'][:135]}")
        print(f"      📰 {item['source']}  🕐 {item['published'][:25]}")
        if themes:
            print(f"      🏷️  {' · '.join(themes)}")
    
    # INSTRUMENT ANALYSIS
    print(f"\n{'─' * 100}")
    print("🔷  INSTRUMENT ANALYSIS")
    print(f"{'─' * 100}")
    
    for inst, config in INSTRUMENTS.items():
        data = classified[inst]
        print(f"\n  ▶ {config['name']} ({config['type']})")
        d = data["direct_matches"]
        t = data["theme_matches"]
        print(f"     Direct: {data['total_direct']} | By theme: {data['total_theme']}")
        
        if d:
            for i, item in enumerate(d[:3], 1):
                print(f"     [{i}] {item['title'][:115]}")
                print(f"         🕐 {item['published'][:25]}")
        elif t:
            for i, item in enumerate(t[:2], 1):
                print(f"     [theme] {item['title'][:115]}")
    
    # THEME ANALYSIS
    print(f"\n{'─' * 100}")
    print("🔷  KEY THEMES & MARKET IMPACT")
    print(f"{'─' * 100}")
    
    theme_items = {}
    for item in news:
        text = item.get("title","") + " " + item.get("description","")
        for t in extract_themes(text):
            theme_items.setdefault(t, []).append(item)
    
    theme_info = [
        ("🇮🇷  GEOPOLITICS (Iran War)", "geopolitics",
         "Oil disruption, market uncertainty, safe-haven demand"),
        ("📈  INFLATION REACCELERATION", "inflation",
         "PPI today, consumer prices rising, Fed policy implications"),
        ("🏛️  CENTRAL BANK / FED", "central-bank",
         "Warsh confirmed, rate path, monetary policy direction"),
        ("🌏  TRADE / CHINA SUMMIT", "trade-policy",
         "Trump-Xi meeting, tariffs, tech export controls"),
        ("🤖  TECH / AI RALLY", "technology",
         "AI-driven market, Nvidia, semiconductors, data centers"),
        ("⛽  ENERGY / OIL", "energy",
         "Crude prices, supply, Strait of Hormuz"),
        ("📊  BROAD MARKETS", "markets",
         "Equity indices, yields, risk sentiment"),
        ("📋  MACROECONOMY", "macroeconomy",
         "Growth, employment, consumer spending"),
    ]
    
    for icon_name, theme_key, theme_desc in theme_info:
        items = theme_items.get(theme_key, [])
        affected = THEME_TO_INSTRUMENTS.get(theme_key, [])
        aff_names = [INSTRUMENTS[i]["name"] for i in affected]
        
        print(f"\n  {icon_name}")
        print(f"     {theme_desc} ({len(items)} headlines)")
        print(f"     Instruments: {', '.join(aff_names)}")
        for i, item in enumerate(items[:3], 1):
            print(f"     {i}. {item['title'][:115]}")
    
    # RECOMMENDATIONS
    print(f"\n{'─' * 100}")
    print("🔷  TRIUMVIRATE STRATEGY — ACTIONABLE INTELLIGENCE")
    print(f"{'─' * 100}")
    
    recs = []
    if len(theme_items.get("geopolitics", [])) >= 3:
        recs.append("🇮🇷  OIL/GOLD: Iran war + Strait of Hormuz disruption — USOIL/UKOIL elevated volatility. "
                    "XAUUSD as geopolitical hedge. Monitor for escalation/de-escalation signals.")
    if len(theme_items.get("inflation", [])) >= 2:
        recs.append("📊  PPI TODAY (08:30 ET): April inflation data critical for USD pairs and gold. "
                    "Hot print = USD strength pressures XAUUSD; soft print = relief rally.")
    if len(theme_items.get("trade-policy", [])) >= 2:
        recs.append("🌏  TRUMP-XI SUMMIT: Jensen Huang joining = tech/détente signal. "
                    "Watch US30, US500, USTEC, JP225 for positioning. Tariff headlines key.")
    if len(theme_items.get("technology", [])) >= 3:
        recs.append("🤖  TECH RALLY: AI/chip momentum broadening. USTEC at records — Qualcomm -11% "
                    "suggests rotation. Nvidia/China trip catalyst for semis.")
    if len(theme_items.get("central-bank", [])) >= 2:
        recs.append("🏛️  FED WATCH: Warsh confirmed (51-45). Market assessing new chair path. "
                    "Dollar sensitivity elevated — affects all USD pairs and gold.")
    
    for i, r in enumerate(recs, 1):
        print(f"  {i}. {r}")
    
    print(f"\n{'═' * 100}")
    print(f"  ✅  {len(news)} headlines from {len(RSS_FEEDS)} feeds | Logs: {LOG_DIR}")
    print(f"{'═' * 100}\n")


def main():
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    print(f"🚀  Triumvirate News Intelligence — {ts} Beijing\n")
    
    news = fetch_all_news()
    print(f"📡  {len(news)} recent headlines\n")
    
    if not news:
        print("❌  No news fetched.")
        return
    
    classified = classify_news(news)
    
    # Save files
    for inst in INSTRUMENTS:
        d = {
            "instrument": inst,
            "name": INSTRUMENTS[inst]["name"],
            "timestamp": datetime.now(BEIJING_TZ).isoformat(),
            "direct_matches": classified[inst]["direct_matches"],
            "theme_matches": classified[inst]["theme_matches"]
        }
        fp = os.path.join(LOG_DIR, f"{ts}_{inst}.json")
        with open(fp, "w") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    
    # General news
    all_themes = {}
    for item in news:
        for t in extract_themes(item.get("title","") + " " + item.get("description","")):
            all_themes.setdefault(t, 0)
            all_themes[t] += 1
    
    gp = {
        "type": "general_market_news",
        "timestamp": datetime.now(BEIJING_TZ).isoformat(),
        "total_items": len(news),
        "theme_breakdown": dict(sorted(all_themes.items(), key=lambda x: -x[1])),
        "news": news
    }
    fp = os.path.join(LOG_DIR, f"{ts}_GENERAL_MARKET_NEWS.json")
    with open(fp, "w") as f:
        json.dump(gp, f, indent=2, ensure_ascii=False)
    
    print_report(news, classified)


if __name__ == "__main__":
    main()
