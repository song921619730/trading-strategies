#!/usr/bin/env python3
"""run_discovery.py — high-rr 研究调用共享发现引擎"""
import sys, os, json
SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "scripts")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")

sys.path.insert(0, SHARED)
from discovery_engine import run_discovery

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="high-rr 发现引擎")
    parser.add_argument("--tf", default="M5", help="M5/M15/H1/H4/D1/W1/MN1")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    result = run_discovery(
        data_dir=DATA_DIR,
        timeframe=args.tf,
        symbols=args.symbols.split(",") if args.symbols else None,
        dry_run=args.dry_run,
        top_n=args.top,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not args.dry_run and result.get("top_findings"):
        os.makedirs(STATE_DIR, exist_ok=True)
        state = {
            "status": result["status"],
            "current_round": "auto_discovery",
            "last_run": __import__("datetime").datetime.utcnow().isoformat(),
            "best_known": result.get("best_known", {}),
            "hypotheses": [], "warnings": [],
            "next_actions": [f"检查 auto_discovery 的 {result['total_findings']} 个发现"],
            "findings_summary": {
                "total": result["total_findings"],
                "duration_s": result["duration_s"],
                "top": [{"condition": r["condition"], "win_rate": r["win_rate"],
                         "n": r["n"], "sharpe": r["sharpe"],
                         "avg_return": r["avg_return"]}
                        for r in result["top_findings"][:10]],
            },
        }
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "discovery_result.json"), "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
