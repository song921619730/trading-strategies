#!/usr/bin/env python3
"""Fix fatigue_count in state - set to 1 (inherited from round18)"""

import json
from pathlib import Path

state_path = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/state/research_state.json")
state = json.loads(state_path.read_text())

state["fatigue_count"] = 1  # inherited from round18 (1/5)

state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(f"✅ Fixed fatigue_count=1. current_round={state['current_round']}")
