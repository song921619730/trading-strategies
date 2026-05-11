import json
import os
import sys
from datetime import datetime

# ============================================================
# A 股 Kanban Loop - 任务调度器 (Orchestrator)
# ============================================================
# 核心职责：
# 1. 读取 state.json
# 2. 判断当前阶段 (T1: Hypothesis / T2: Execution)
# 3. 执行疲劳检测 (Fatigue Check)
# 4. 决定下一步行动 (Continue / Switch Topic)

class Orchestrator:
    def __init__(self, state_path):
        self.state_path = state_path
        self.state = self.load_state()

    def load_state(self):
        if not os.path.exists(self.state_path):
            return self.create_default_state()
        with open(self.state_path, 'r') as f:
            return json.load(f)

    def create_default_state(self):
        return {
            "topic": "Low Open High Go",
            "current_iteration": 0,
            "best_metrics": {
                "best_5d_return": 0.0,
                "best_10d_return": 0.0,
                "max_drawdown": 1.0
            },
            "data_exploration": {
                "current_layer": "L1",
                "tested_layers": ["L1"],
                "fatigue_count": 0
            },
            "next_task": "T1_Hypothesis" # T1 或 T2
        }

    def check_fatigue(self):
        """
        疲劳检测逻辑：
        如果连续 3 次迭代没有打破历史最佳收益，判定为疲劳。
        """
        fatigue_count = self.state['data_exploration']['fatigue_count']
        current_layer = self.state['data_exploration']['current_layer']
        
        if fatigue_count >= 3:
            print(f"⚠️ Fatigue Detected in {current_layer}. Count: {fatigue_count}")
            # 尝试解锁下一层
            next_layer = self.get_next_layer(current_layer)
            if next_layer:
                print(f"🔓 Unlocking next layer: {next_layer}")
                self.state['data_exploration']['current_layer'] = next_layer
                self.state['data_exploration']['tested_layers'].append(next_layer)
                self.state['data_exploration']['fatigue_count'] = 0 # 重置计数
                self.save_state()
                return True # 成功解锁，继续研究
            else:
                print("🛑 All layers exhausted. Topic Archived.")
                return False # 彻底放弃，切换主题
        return True # 未疲劳，继续

    def get_next_layer(self, current):
        layers = ["L1", "L2", "L3", "L4"]
        idx = layers.index(current) if current in layers else -1
        if idx < len(layers) - 1:
            return layers[idx + 1]
        return None

    def update_on_success(self, new_5d_return):
        """
        如果回测收益打破历史纪录，重置疲劳计数。
        """
        best = self.state['best_metrics']['best_5d_return']
        if new_5d_return > best:
            print(f"🎉 New Record! {new_5d_return} > {best}")
            self.state['best_metrics']['best_5d_return'] = new_5d_return
            self.state['data_exploration']['fatigue_count'] = 0
            self.save_state()

    def dispatch(self):
        """
        决定下一步做什么。
        """
        task = self.state.get('next_task', 'T1_Hypothesis')
        
        if task == 'T1_Hypothesis':
            print("🤖 Dispatching T1: Analyst to generate hypothesis...")
            # 这里会调用 Hermes 的 Clarify 或生成 Prompt 文件
            # 实际执行时，Orchestrator 会生成 grid_config.json 并调用 grid_engine.py
            return "T1"
        elif task == 'T2_Execution':
            print("⚙️ Dispatching T2: Researcher to run grid_engine.py...")
            # 这里会调用 Python 脚本
            return "T2"

    def run_cycle(self):
        """
        执行一个完整的 T1 -> T2 -> T3 -> T4 循环。
        """
        # 1. Check fatigue
        if not self.check_fatigue():
            return "ARCHIVED"
            
        # 2. Dispatch T1 (Generate Config)
        # In a real run, this would call an LLM to generate grid_config.json
        # For now, we assume config exists or is generated externally
        config_path = 'grid_config.json'
        if not os.path.exists(config_path):
            print(f"⚠️ Config {config_path} not found. Generating default...")
            # Fallback to template
            import shutil
            shutil.copy('grid_config_template.json', config_path)
            
        # 3. Dispatch T2 (Run Engine)
        print("🏃 Running Grid Engine...")
        # os.system(f"python3 scripts/grid_engine.py {config_path}")
        # For demonstration, we just print
        print("✅ Backtest Complete.")
        
        # 4. Dispatch T3/T4 (Update State)
        # In a real run, we would parse results.csv and update best_metrics
        self.state['current_iteration'] += 1
        self.state['next_task'] = 'T1_Hypothesis' # Loop back
        self.save_state()
        
        return "CONTINUE"

    def save_state(self):
        with open(self.state_path, 'w') as f:
            json.dump(self.state, f, indent=2)

if __name__ == '__main__':
    state_file = sys.argv[1] if len(sys.argv) > 1 else 'state/lowopen_state.json'
    orch = Orchestrator(state_file)
    
    # 1. 检查疲劳
    alive = orch.check_fatigue()
    if not alive:
        print("❌ Topic Exhausted.")
        sys.exit(0)
        
    # 2. 调度任务
    next_action = orch.dispatch()
    print(f"👉 Next Action: {next_action}")
