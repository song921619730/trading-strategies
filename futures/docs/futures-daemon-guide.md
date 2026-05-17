# Futures Daemon 运维指南

## 架构总览

期货实时交易系统采用 **1 + N 配置驱动架构**：

```
daemon/
├── daemon.json         ← 策略注册表（新增策略只改这里）
└── config_reader.py    ← JSON → bash 变量（自动转换）

scripts/
└── auto_launch_all.sh  ← 配置驱动启动器（读 JSON，管 tmux + systemd）
```

运行时：

```
                 ┌──────────────────────────┐
                 │   Tick Engine            │
                 │   (唯一连接 MT5)          │
                 │   1s 循环 ✦ 15品种 × 5TF  │
                 └──────────┬───────────────┘
                            │
                    data/tick/ (JSON 共享层)
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
  ┌──────────┐    ┌──────────────┐    ┌──────────────┐
  │ Scalping │    │ Intraday     │    │ 新策略..     │
  │ Autopilot│    │ Autopilot    │    │              │
  │ M1/M5    │    │ M30/H1       │    │ 加一行 JSON   │
  └──────────┘    └──────────────┘    └──────────────┘
```

每个组件由 **tmux** 管理生命周期，**systemd** 保证开机自启，**自愈循环**保证崩溃恢复。

## 策略注册表

所有策略定义在 `daemon/daemon.json`：

```json
{
  "python": "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe",
  "base": "F:/AIcoding_space/Hermes/strategies/futures",
  "session_prefix": "futures-daemon",
  "log_dir": "logs",
  "default_restart_delay": 3,
  "strategies": {
    "tick-engine": {
      "description": "数据引擎 — 唯一连接 MT5，1s 循环写入共享 JSON",
      "script": "scripts/tick_engine.py",
      "restart_delay": 3
    },
    "scalping-ap": {
      "description": "M1/M5 Scalping 自动交易 (Magic 234011)",
      "script": "single-agent/scalping/scripts/scalping_autopilot.py",
      "restart_delay": 3
    },
    "intraday-ap": {
      "description": "M30/H1 Intraday 自动交易 (Magic 234010)",
      "script": "single-agent/futures-intraday/scripts/intraday_autopilot.py",
      "restart_delay": 3
    }
  }
}
```

### 添加新策略

```json
// 在 "strategies" 对象里加一条：
"high-rr-ap": {
    "description": "高盈亏比策略",
    "script": "single-agent/high-rr/scripts/high_rr_autopilot.py",
    "restart_delay": 5
}
```

### 移除策略

```json
// 直接删掉对应条目即可
```

## 进程管理

### 管理脚本

```bash
bash F:/AIcoding_space/Hermes/strategies/futures/scripts/auto_launch_all.sh {start|stop|restart|status|attach}
```

脚本自动读取 `daemon/daemon.json`，无需硬编码任何策略名。

### 查看实时日志

```bash
# 方法1: attach 到 tmux 会话（交互选择）
bash auto_launch_all.sh attach

# 方法2: 直接 capture（适合脚本）
tmux capture-pane -t futures-daemon-tick-engine -p | tail -20

# 方法3: 看日志文件
tail -f F:/AIcoding_space/Hermes/strategies/futures/logs/tick-engine.log
```

### 查看状态

```bash
bash auto_launch_all.sh status
# 输出示例:
# === 期货后台守护进程状态 (3 策略) ===
#   🟢 intraday-ap        (pid=85218) M30/H1 Intraday 自动交易 (Magic 234010)
#   🟢 scalping-ap        (pid=85230) M1/M5 Scalping 自动交易 (Magic 234011)
#   🟢 tick-engine        (pid=85245) 数据引擎 — 唯一连接 MT5，1s 循环写入共享 JSON
```

### 添加/移除策略后的操作

改完 `daemon/daemon.json` 后重启即可：

```bash
bash auto_launch_all.sh restart
```

## 自愈机制

每个进程运行在 `while true` 循环中，崩溃后自动重启（延迟 `restart_delay` 秒），且重启前自动杀残留 Windows 进程：

```
[auto-launch] === 2026-05-13 14:21:41 UTC Starting tick-engine ===
[TickEngine] [10] ticks=15/15 indicators=75 errors=0 uptime=9s
[auto-launch] === 2026-05-13 14:21:55 UTC tick-engine exited (rc=2), restarting in 3s ===
[auto-launch] === 2026-05-13 14:21:58 UTC Starting tick-engine ===
```

### 防重复三重机制

| 层级 | 位置 | 做了什么 |
|------|------|---------|
| 1️⃣ 启动前杀 | `start_one()` | 每次创建 tmux 前，wmic 杀同名脚本的 Windows 残留进程 |
| 2️⃣ 停止时清 | `stop_all()` | stop/restart 时同时杀 tmux 会话 + Windows 同名进程 |
| 3️⃣ 脚本自护 | `config_reader.py` | `stop` 和 `restart` 都调用 `stop_all`，不依赖 JSON 条目 |

即使 JSON 已删除条目的孤儿 tmux 会话，`stop_all` 也会按 `futures-daemon-` 前缀全清。

## systemd 开机自启

```bash
# 启用（已配置）
systemctl --user enable futures-daemon.service

# 查看状态
systemctl --user status futures-daemon.service

# 查看日志
journalctl --user -u futures-daemon.service -n 50 --no-pager

# 重启
systemctl --user restart futures-daemon.service
```

WSL 重启后策略自动恢复，无需人工介入。

## 配置文件架构

```
daemon/
├── daemon.json          ← 策略注册表（人类可读）
└── config_reader.py     ← 配置解析器（JSON → bash 变量）
```

`config_reader.py` 将 `daemon.json` 转换为 bash 的索引式变量：

| bash 变量 | 说明 |
|-----------|------|
| `DAEMON_NUM` | 策略数量 |
| `DAEMON_PREFIX` | tmux 会话名前缀 |
| `DAEMON_LOG_DIR` | 日志目录 |
| `DAEMON_NAME_{i}` | 第 i 个策略名称 |
| `DAEMON_CMD_{i}` | 第 i 个策略完整命令 |
| `DAEMON_DELAY_{i}` | 第 i 个策略重启延迟 |
| `DAEMON_DESC_{i}` | 第 i 个策略描述 |

测试解析器输出：

```bash
eval "$(python3 F:/AIcoding_space/Hermes/strategies/futures/daemon/config_reader.py)"
echo "策略数: $DAEMON_NUM"
for i in $(seq 0 $((DAEMON_NUM - 1))); do
    v="DAEMON_NAME_$i"; echo "  ${!v}: $(eval echo \$DAEMON_DESC_$i)"
done
```

## 添加新策略（完整示例）

### 场景

你开发了一个新的 `high-rr` 策略，想让守护进程自动管理。

### 前提

策略已经有了可执行脚本 `high_rr_autopilot.py`，并能读取 `data/tick/` 共享数据。

### 步骤

#### 1. 编辑 `daemon/daemon.json`

在 `strategies` 对象里加一条：

```json
"high-rr-ap": {
    "description": "高盈亏比自动交易 (Magic 234012)",
    "script": "single-agent/high-rr/scripts/high_rr_autopilot.py",
    "restart_delay": 5
}
```

#### 2. 重启守护进程

```bash
bash F:/AIcoding_space/Hermes/strategies/futures/scripts/auto_launch_all.sh restart
```

#### 3. 验证

```bash
bash auto_launch_all.sh status
# 应看到: 🟢 high-rr-ap ...

# 确认 Windows 进程
wmic process where "name='python.exe' and CommandLine like '%high_rr%'" get ProcessId /format:csv
```

### 完成效果

新策略自动享受完整能力：

| 能力 | 说明 |
|------|------|
| ✅ tmux 隔离 | 独立会话，不影响其他进程 |
| ✅ 自愈重启 | 崩溃后 N 秒自动拉起 |
| ✅ 日志留存 | `logs/{name}.log` |
| ✅ systemd 开机自启 | WSL 重启后自动恢复 |
| ✅ 统一管理 | status/stop/restart/attach 一键操作 |
| ✅ 配置驱动 | 改 JSON 而已，不动脚本 |

## 路径规则（重要）

| 变量 | 格式 | 原因 |
|------|------|------|
| `python` | `/mnt/c/Users/.../python.exe` | WSL bash 通过 `/mnt/` 找 Windows 可执行文件 |
| `base` | `F:/AIcoding_space/...` | Windows Python 识别 `F:/` 格式路径 |
| `script` | `scripts/tick_engine.py` | 拼接在 base 后面，相对路径 |

**不要**用 `C:\` 反斜杠格式，bash 不识别。
**不要**在 `script` 里加完整路径，脚本自动拼接 `base + script`。

## 故障排查

### 进程反复重启

```bash
# attach 看实时输出
bash auto_launch_all.sh attach
```

常见原因：
- **单引号边界破坏**：检查 wrapper 里是否有 `'` 字符。date 格式必须用双引号 `"+"%Y-%m-%d..."`
- **路径错误**：`python` 用 `/mnt/c/...`，脚本相对路径不用改
- **PermissionError**：`tick_engine.py` 的 `atomic_write` 已兼容

### tmux 会话闪退

```bash
# 试试直接创建最小 tmux 看是否正常
tmux new-session -d -s test-issue "echo hello; sleep 5"
tmux has-session -t test-issue && echo "tmux OK" || echo "tmux 异常"
```

### systemd 状态异常

```bash
# 查看错误日志
journalctl --user -u futures-daemon.service -n 50 --no-pager

# 重启服务
systemctl --user restart futures-daemon.service
```

### 进程重复（两个 scalping-ap 实例）

```
症状:   status 显示 scalping-ap 虽绿但有 2 个 Windows Python 进程
原因:   旧版单独 scalping-autopilot.service 仍启用，与新 daemon 打架
          该服务有 Restart=always，10s 自动重启
解决:   禁用旧服务
systemctl --user disable scalping-autopilot.service
systemctl --user stop scalping-autopilot.service
```

> 注：`futures-daemon.service` 上线后，旧的独立服务（scalping-autopilot、intraday-autopilot）已废弃。
> 所有策略改由 `daemon/daemon.json` 统一管理。若残留旧服务，禁用即可。

### 手动 kill 后重启

```bash
bash auto_launch_all.sh restart
```

### 旧系统服务冲突检查

```bash
# 检查是否有残留的旧独立服务
systemctl --user list-units 2>/dev/null | grep -E "scalping|intraday"
# 如有输出（如 scalping-autopilot.service），禁用：
systemctl --user disable <服务名>
systemctl --user stop <服务名>
```

## 快速验证

部署后运行以下命令确认系统正常：

```bash
# 1. 状态检查 — 所有策略绿色
bash auto_launch_all.sh status

# 2. 无重复进程 — 每个策略应刚好 1 个 Windows 进程
wmic process where "name='python.exe' and (CommandLine like '%tick_engine%' or CommandLine like '%autopilot%')" get ProcessId,CreationDate,CommandLine /format:csv

# 3. 数据健康 — errors=0
python3 -c "import json; h=json.load(open('F:/AIcoding_space/Hermes/strategies/futures/data/tick/_heartbeat.json')); print(f'errors={h.get(\"errors\",\"?\")}')"

# 4. 测试添加删除（可选）
#    → 改 daemon.json 加一条 test 条目
#    → bash auto_launch_all.sh restart
#    → 确认新策略出现
#    → 删除 JSON 条目 → restart
#    → 确认回到原状态，无孤儿
```
