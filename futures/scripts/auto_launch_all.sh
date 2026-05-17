#!/usr/bin/env bash
# ============================================================
# auto_launch_all.sh — 配置驱动期货后台守护进程
# 用途: 读取 daemon/daemon.json → tmux 管理 → 自愈循环
# 新增策略只改 JSON，重启即可
# 用法:
#   bash auto_launch_all.sh            # 启动全部
#   bash auto_launch_all.sh status     # 查看状态
#   bash auto_launch_all.sh stop       # 停止全部
#   bash auto_launch_all.sh attach     # attach 到某个进程日志
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DAEMON_DIR="$(cd "$SCRIPT_DIR/../daemon" && pwd)"

# ─── 从 daemon.json 读取配置 ───
eval "$(python3 "$DAEMON_DIR/config_reader.py")"
if [[ $DAEMON_NUM -lt 1 ]]; then
    echo "[ERROR] daemon/daemon.json 中没有定义策略" >&2
    exit 1
fi

mkdir -p "$DAEMON_LOG_DIR"

# 根据索引取配置
get_name()  { local v="DAEMON_NAME_$1";  echo "${!v}"; }
get_cmd()   { local v="DAEMON_CMD_$1";   echo "${!v}"; }
get_delay() { local v="DAEMON_DELAY_$1"; echo "${!v}"; }
get_desc()  { local v="DAEMON_DESC_$1";  echo "${!v}"; }

SESSION_PREFIX="$DAEMON_PREFIX"

tmux_has_session() {
    tmux has-session -t "$1" 2>/dev/null
}

start_one() {
    local i="$1"
    local name desc cmd delay full_session

    name=$(get_name "$i")
    desc=$(get_desc "$i")
    cmd=$(get_cmd "$i")
    delay=$(get_delay "$i")
    full_session="${SESSION_PREFIX}-${name}"

    # 先杀残留的 Windows 进程（防止孤儿进程重复）
    local script
    script=$(python3 -c "import json; print(json.load(open('$DAEMON_DIR/daemon.json'))['strategies']['$name']['script'])" 2>/dev/null)
    [[ -n "$script" ]] && /mnt/c/Windows/System32/wbem/wmic.exe process where \
        "name='python.exe' and CommandLine like '%${script}%'" delete 2>/dev/null || true
    sleep 0.5

    if tmux_has_session "$full_session"; then
        echo "  ⏩ $name 已在运行 $([[ -n "$desc" ]] && echo "($desc)")"
        return 0
    fi

    # 自愈循环包装
    # 注意: date 格式用双引号避免破坏 bash -c 的单引号边界
    local wrapper="while true; do
        echo \"[auto-launch] === \$(date -u \"+%Y-%m-%d %H:%M:%S UTC\") Starting $name ===\"
        $cmd
        rc=\$?
        echo \"[auto-launch] === \$(date -u \"+%Y-%m-%d %H:%M:%S UTC\") $name exited (rc=\$rc), restarting in ${delay}s ===\"
        sleep $delay
    done"

    tmux new-session -d -s "$full_session" "exec bash -c '$wrapper'"
    echo "  ✅ $name 已启动 $([[ -n "$desc" ]] && echo "($desc)")"
}

stop_one() {
    local i="$1"
    local name full_session
    name=$(get_name "$i")
    full_session="${SESSION_PREFIX}-${name}"

    if tmux_has_session "$full_session"; then
        tmux kill-session -t "$full_session"
        echo "  🛑 $name 已停止"
    else
        echo "  ⚪ $name 未运行"
    fi
}

status_all() {
    echo "=== 期货后台守护进程状态 (${DAEMON_NUM} 策略) ==="
    for i in $(seq 0 $((DAEMON_NUM - 1))); do
        local name desc full_session
        name=$(get_name "$i")
        desc=$(get_desc "$i")
        full_session="${SESSION_PREFIX}-${name}"

        if tmux_has_session "$full_session"; then
            local pid uptime
            pid=$(tmux list-panes -t "$full_session" -F '#{pane_pid}' 2>/dev/null)
            uptime=$(tmux list-panes -t "$full_session" -F '#{session_created}' 2>/dev/null)
            printf "  🟢 %-18s (pid=%-5s) %s\n" "$name" "$pid" "$desc"
        else
            printf "  🔴 %-18s (已停止)     %s\n" "$name" "$desc"
        fi
    done
    echo "---"
    echo "tmux sessions:"
    tmux ls 2>/dev/null | grep "$SESSION_PREFIX" || echo "(无)"
    echo ""
    echo "配置来源: $DAEMON_DIR/daemon.json"
}

attach_menu() {
    echo "选择一个进程查看实时日志:"
    local names=()
    for i in $(seq 0 $((DAEMON_NUM - 1))); do
        names+=("$(get_name "$i")")
        echo "  $((i+1))) ${names[$i]}"
    done
    echo -n "输入编号 (1-${DAEMON_NUM}): "
    read -r sel
    if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -le "$DAEMON_NUM" ]; then
        tmux attach-session -t "${SESSION_PREFIX}-${names[$((sel-1))]}"
    else
        echo "无效选择"
    fi
}

# ─── 停止所有（含已从 JSON 移除的孤儿会话和 Windows 进程）───
stop_all() {
    # 1. 杀 tmux 会话
    local sessions
    sessions=$(tmux ls 2>/dev/null | grep "^${SESSION_PREFIX}-" | cut -d: -f1)
    if [[ -n "$sessions" ]]; then
        while IFS= read -r s; do
            [[ -z "$s" ]] && continue
            tmux kill-session -t "$s"
            local short_name="${s#${SESSION_PREFIX}-}"
            echo "  🛑 $short_name 已停止"
        done <<< "$sessions"
    else
        echo "  (无运行中的 tmux 会话)"
    fi

    # 2. 杀 Windows 孤儿 Python 进程（确保完全清理）
    # 根据脚本路径匹配（Windows 命令行也用 /）
    for i in $(seq 0 $((DAEMON_NUM - 1))); do
        local name script
        name=$(get_name "$i")
        script=$(python3 -c "import json; print(json.load(open('$DAEMON_DIR/daemon.json'))['strategies']['$name']['script'])")
        /mnt/c/Windows/System32/wbem/wmic.exe process where \
            "name='python.exe' and CommandLine like '%${script}%'" delete 2>/dev/null || true
    done
}

case "${1:-start}" in
    start)
        echo "🚀 启动期货后台守护进程 (${DAEMON_NUM} 策略)..."
        for i in $(seq 0 $((DAEMON_NUM - 1))); do
            start_one "$i"
        done
        echo ""
        status_all
        ;;
    stop)
        echo "🛑 停止所有期货后台进程..."
        stop_all
        ;;
    restart)
        echo "🔄 重启所有进程..."
        stop_all
        sleep 2
        exec bash "$0" start
        ;;
    status)
        status_all
        ;;
    attach)
        attach_menu
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|attach}"
        exit 1
        ;;
esac
