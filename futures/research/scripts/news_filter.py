#!/usr/bin/env python3
"""
News Filter — 高信噪比新闻摘要生成器
从 News Pipeline (9 数据源) 拉取原始新闻，做去重、评分、聚类，
输出结构化的"事件摘要"供 Research AI 参考。

过滤规则：
1. 去重：相似标题合并（Jaccard 相似度 > 0.4）
2. 评分：基于关键词、源可信度、时间新鲜度
3. 聚类：按事件主题分组
4. 只输出 score > threshold 的高价值事件
"""

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict
import re

# ============ Config ============
NEWS_API = "http://127.0.0.1:8900"

# 高价值关键词（交易/研究相关）
HIGH_SIGNAL_KEYWORDS = [
    # 宏观/央行
    "美联储", "加息", "降息", "CPI", "PPI", "非农", "PMI", "GDP", "通胀", "衰退",
    "欧央行", "日本央行", "中国人民银行", "央行", "MLF", "LPR", "降准", "逆回购",
    # 地缘政治
    "战争", "制裁", "关税", "贸易", "出口管制", "冲突", "霍尔木兹", "红海",
    # 商品/能源
    "OPEC", "减产", "库存", "EIA", "API", "战略储备", "供应中断", "罢工",
    "干旱", "洪水", "厄尔尼诺", "种植面积",
    # 市场异动
    "暴涨", "暴跌", "涨停", "跌停", "突破", "崩盘", "熔断", "流动性",
    # A 股政策
    "证监会", "IPO", "退市", "注册制", "全面注册", "国家队", "北向", "南向",
    # 财报/事件
    "财报", "业绩", "超预期", "不及预期", "暴雷", "重组", "并购", "定增",
]

# 中等价值关键词
MED_SIGNAL_KEYWORDS = [
    "涨停", "跌停", "连板", "换手", "放量", "缩量", "资金流向",
    "主力", "散户", "机构", "调研", "评级", "目标价",
    "黄金", "白银", "原油", "铜", "铁矿石", "焦炭", "焦煤", "螺纹钢",
    "芯片", "半导体", "新能源", "AI", "人工智能", "光伏", "锂电",
]

# 源可信度权重
SOURCE_WEIGHTS = {
    "bloomberg": 1.0, "reuters": 1.0, "jin10": 0.9, "wallstreetcn": 0.9,
    "eastmoney": 0.8, "cls": 0.8, "sinafinance": 0.7,
    "10jqka": 0.7, "bbc": 0.6,
}

# 噪音关键词（降低评分）
NOISE_KEYWORDS = ["个股", "公告", "股东减持", "增持", "解禁", "中签",
                  "研报", "评级上调", "评级下调", "目标价"]


def jaccard_similarity(s1, s2):
    """计算两个字符串的 Jaccard 相似度"""
    set1 = set(s1)
    set2 = set(s2)
    if not set1 or not set2:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


def deduplicate_news(items, threshold=0.4):
    """去重：合并相似标题的新闻"""
    clusters = []  # list of lists
    for item in items:
        title = item.get("title", "")
        placed = False
        for cluster in clusters:
            existing = cluster[0].get("title", "")
            if jaccard_similarity(title, existing) > threshold:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def score_cluster(cluster, max_age_hours=24):
    """对一个新闻簇评分"""
    if not cluster:
        return 0
    
    item = cluster[0]  # 用第一条代表
    title = item.get("title", "").lower()
    summary = item.get("summary", "").lower()
    source = item.get("source", "")
    
    # 1. 关键词评分
    kw_score = 0
    matched_kws = []
    text = title + summary
    for kw in HIGH_SIGNAL_KEYWORDS:
        if kw.lower() in text:
            kw_score += 3
            matched_kws.append(kw)
    for kw in MED_SIGNAL_KEYWORDS:
        if kw.lower() in text:
            kw_score += 1
            matched_kws.append(kw)
    # 噪音扣分
    for kw in NOISE_KEYWORDS:
        if kw.lower() in text:
            kw_score -= 2
    
    # 2. 源可信度
    source_weight = SOURCE_WEIGHTS.get(source, 0.5)
    
    # 3. 时间新鲜度 (越近越好)
    try:
        pub_time = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(pub_time.tzinfo) - pub_time).total_seconds() / 3600
        freshness = max(0, 1 - (age_hours / max_age_hours))
    except:
        freshness = 0.5
    
    # 4. 多源确认加分 (多个独立源报道同一事件 = 可信度高)
    sources_in_cluster = set(i.get("source") for i in cluster)
    multi_source_bonus = min(len(sources_in_cluster) * 0.5, 2.0)
    
    total = (kw_score * source_weight * freshness) + multi_source_bonus
    return {
        "score": round(total, 1),
        "matched_keywords": list(set(matched_kws)),
        "source_count": len(sources_in_cluster),
        "sources": sorted(sources_in_cluster),
    }


def fetch_news(categories=None, minutes=1440, limit=200):
    """从 News Pipeline 拉取新闻"""
    all_items = []
    cats = categories or ["futures", "forex", "a_shares", "global_macro"]
    
    for cat in cats:
        try:
            url = f"{NEWS_API}/api/v1/news/latest"
            params = {"minutes": minutes, "category": cat, "limit": limit}
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            if data.get("success"):
                all_items.extend(data.get("data", []))
        except Exception as e:
            print(f"⚠️ Failed to fetch {cat}: {e}")
    
    # 按时间排序（新到旧）
    all_items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_items


def filter_and_summarize(categories=None, minutes=1440, min_score=3.0, max_events=15):
    """主函数：拉取 → 去重 → 评分 → 输出摘要"""
    print(f"📡 Fetching news (categories={categories}, minutes={minutes})...")
    raw = fetch_news(categories, minutes)
    print(f"📥 Raw items: {len(raw)}")
    
    # 去重
    clusters = deduplicate_news(raw, threshold=0.4)
    print(f"🔗 After dedup: {len(clusters)} clusters")
    
    # 评分
    scored = []
    for cluster in clusters:
        scoring = score_cluster(cluster)
        scored.append({
            "cluster": cluster,
            **scoring,
        })
    
    # 过滤 + 排序
    scored = [s for s in scored if s["score"] >= min_score]
    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:max_events]
    
    print(f"📊 High-signal events: {len(scored)}")
    return scored


def to_markdown(events, title_prefix="News"):
    """转换为 Markdown 摘要"""
    md = f"## 📰 {title_prefix}: High-Signal Events\n\n"
    
    if not events:
        md += "> No significant market-moving events detected in the selected window.\n"
        return md
    
    for i, ev in enumerate(events, 1):
        item = ev["cluster"][0]
        pub_time = item.get("published_at", "?")[:16].replace("T", " ")
        
        md += f"### {i}. {item['title']}  `Score: {ev['score']}`\n"
        md += f"- **时间**: {pub_time} UTC\n"
        md += f"- **来源**: {', '.join(ev['sources'])} ({ev['source_count']} 源)\n"
        if ev['matched_keywords']:
            md += f"- **关键词**: {', '.join(ev['matched_keywords'][:5])}\n"
        # 摘要（截断）
        summary = item.get("summary", "")
        if len(summary) > 300:
            summary = summary[:300] + "..."
        if summary:
            md += f"- **摘要**: {summary}\n"
        # 多源补充信息
        if len(ev["cluster"]) > 1:
            extra = []
            for c in ev["cluster"][1:3]:  # 最多展示 2 个补充
                if c.get("title") != item.get("title"):
                    extra.append(f"- 补充: {c['title']} ({c.get('source', '?')})")
            if extra:
                md += "\n".join(extra) + "\n"
        md += "\n"
    
    md += "---\n*Filtered from raw feed: dedup + keyword scoring + multi-source confirmation*\n"
    return md


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--categories", nargs="+", default=None,
                        help="News categories to fetch")
    parser.add_argument("--minutes", type=int, default=1440,
                        help="Time window in minutes (default: 24h)")
    parser.add_argument("--min-score", type=float, default=3.0,
                        help="Minimum score threshold")
    parser.add_argument("--max-events", type=int, default=15,
                        help="Max events to output")
    parser.add_argument("--markdown", action="store_true",
                        help="Output as markdown")
    args = parser.parse_args()
    
    events = filter_and_summarize(
        categories=args.categories,
        minutes=args.minutes,
        min_score=args.min_score,
        max_events=args.max_events,
    )
    
    if args.markdown:
        print("\n" + to_markdown(events))
    else:
        print(json.dumps([{
            "title": e["cluster"][0].get("title"),
            "score": e["score"],
            "sources": e["sources"],
            "keywords": e["matched_keywords"],
        } for e in events], ensure_ascii=False, indent=2))
