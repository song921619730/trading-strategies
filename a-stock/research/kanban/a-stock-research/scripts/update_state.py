#!/usr/bin/env python3
"""
update_state.py — research_state.json 更新工具

用法:
    python3 update_state.py --set-current-round 3
    python3 update_state.py --add-finding '{"id":"...", "win_rate":0.56, ...}'
    python3 update_state.py --update-shadow '{"id":"...", "shadow":{...}}'
    python3 update_state.py --increment-fatigue
    python3 update_state.py --reset-fatigue
    python3 update_state.py --add-hypothesis '{"id":"h_001", "hypothesis":"..."}'
    python3 update_state.py --pop-hypothesis
    python3 update_state.py --get
"""

import json
import sys
import os
from copy import deepcopy

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "state", "research_state.json"
)


def load() -> dict:
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def set_current_round(n: int):
    state = load()
    state["current_round"] = n
    save(state)
    print(f"current_round → {n}")


def add_finding(finding: dict):
    state = load()
    # 去重：同 id 的替换
    ids = [f["id"] for f in state["best_findings"]]
    if finding["id"] in ids:
        idx = ids.index(finding["id"])
        state["best_findings"][idx] = finding
        action = "updated"
    else:
        state["best_findings"].append(finding)
        action = "added"
    save(state)
    print(f"Finding {finding['id']} {action}")


def update_shadow(shadow_data: dict):
    """更新 finding 的 shadow 跟踪数据"""
    state = load()
    finding_id = shadow_data.get("id")
    for f in state["best_findings"]:
        if f["id"] == finding_id:
            f["shadow"] = shadow_data.get("shadow", {})
            save(state)
            print(f"Shadow updated for {finding_id}")
            return
    print(f"Finding {finding_id} not found")


def increment_fatigue():
    state = load()
    state["fatigue_count"] = state.get("fatigue_count", 0) + 1
    save(state)
    print(f"fatigue_count → {state['fatigue_count']}")


def reset_fatigue():
    state = load()
    state["fatigue_count"] = 0
    save(state)
    print("fatigue_count → 0")


def add_hypothesis(h: dict):
    state = load()
    state.setdefault("hypothesis_queue", []).append(h)
    save(state)
    print(f"Hypothesis {h.get('id')} added")


def pop_hypothesis() -> dict | None:
    """弹出队列第一个假设"""
    state = load()
    queue = state.get("hypothesis_queue", [])
    if queue:
        h = queue.pop(0)
        state["hypothesis_queue"] = queue
        # 记录到历史
        state.setdefault("hypothesis_history", []).append(h)
        save(state)
        print(f"Popped hypothesis: {h.get('id')}")
        print(json.dumps(h, ensure_ascii=False))
        return h
    print("hypothesis_queue is empty")
    return None


def increment_analyst_coverage(analyst_name: str):
    state = load()
    cov = state.get("analyst_coverage", {})
    cov[analyst_name] = cov.get(analyst_name, 0) + 1
    state["analyst_coverage"] = cov
    save(state)
    print(f"{analyst_name} coverage → {cov[analyst_name]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-current-round", type=int)
    parser.add_argument("--add-finding", type=str)
    parser.add_argument("--update-shadow", type=str)
    parser.add_argument("--increment-fatigue", action="store_true")
    parser.add_argument("--reset-fatigue", action="store_true")
    parser.add_argument("--add-hypothesis", type=str)
    parser.add_argument("--pop-hypothesis", action="store_true")
    parser.add_argument("--increment-coverage", type=str)
    parser.add_argument("--get", action="store_true", help="打印当前 state")
    args = parser.parse_args()

    if args.set_current_round:
        set_current_round(args.set_current_round)
    elif args.add_finding:
        add_finding(json.loads(args.add_finding))
    elif args.update_shadow:
        update_shadow(json.loads(args.update_shadow))
    elif args.increment_fatigue:
        increment_fatigue()
    elif args.reset_fatigue:
        reset_fatigue()
    elif args.add_hypothesis:
        add_hypothesis(json.loads(args.add_hypothesis))
    elif args.pop_hypothesis:
        pop_hypothesis()
    elif args.increment_coverage:
        increment_analyst_coverage(args.increment_coverage)
    elif args.get:
        print(json.dumps(load(), ensure_ascii=False, indent=2))
    else:
        parser.print_help()
