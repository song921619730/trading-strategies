#!/usr/bin/env python3
"""
daemon/config_reader.py — 读取 daemon.json 输出 bash-eval 格式变量
用法: eval "$(python3 path/to/config_reader.py)"
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "daemon.json")
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

py = cfg["python"]
base = cfg["base"]
prefix = cfg["session_prefix"]
log_dir = f"{base}/{cfg['log_dir']}"
default_delay = cfg.get("default_restart_delay", 3)

strategies = cfg["strategies"]
names = sorted(strategies.keys())

# 固定配置
print(f'DAEMON_PREFIX="{prefix}"')
print(f'DAEMON_LOG_DIR="{log_dir}"')
print(f'DAEMON_NUM={len(names)}')

# 索引式变量: DAEMON_NAME_0, DAEMON_CMD_0, DAEMON_DELAY_0, DAEMON_DESC_0 ...
for i, name in enumerate(names):
    s = strategies[name]
    cmd = f'{py} "{base}/{s["script"]}"'
    escaped_cmd = cmd.replace('"', '\\"')
    delay = s.get("restart_delay", default_delay)
    desc = s.get("description", "").replace('"', '\\"')

    print(f'DAEMON_NAME_{i}="{name}"')
    print(f'DAEMON_CMD_{i}="{escaped_cmd}"')
    print(f'DAEMON_DELAY_{i}={delay}')
    print(f'DAEMON_DESC_{i}="{desc}"')
