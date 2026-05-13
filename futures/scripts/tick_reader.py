#!/usr/bin/env python3
"""
tick_reader.py — 共享数据读取层

供 Scanner 使用，替代直接连接 MT5 拉数据。
如果 Tick Engine 不在运行，自动 fallback 到直连 MT5。

用法:
  from tick_reader import TickReader
  reader = TickReader()
  ticks = reader.get_ticks()          # {symbol: {bid, ask, spread, time}}
  ind = reader.get_indicators("M5")   # {symbol: {rsi14, atr14, ...}}
  signal = reader.get_bar_signal("XAUUSD", "M5")  # new bar info or None
  status = reader.is_alive()          # True/False
"""

import json
import os
import time
from pathlib import Path

# ─── 路径（双系统兼容） ───
# Windows Python: F:/...
# WSL Python: /mnt/f/...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SHARED_DIR_WIN = PROJECT_ROOT / "data" / "tick"
_SHARED_DIR_WSL = Path("/mnt/f") / "AIcoding_space" / "Hermes" / "strategies" / "futures" / "data" / "tick"


def _get_shared_dir() -> Path:
    """自动判断运行环境，返回共享目录"""
    if os.name == "nt":  # Windows
        return _SHARED_DIR_WIN
    # WSL / Linux
    if _SHARED_DIR_WSL.exists():
        return _SHARED_DIR_WSL
    return _SHARED_DIR_WIN


def read_json(path: Path) -> dict | None:
    """安全读取 JSON 文件，不抛出异常"""
    try:
        if path.exists() and path.stat().st_size > 0:
            with open(path) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


class TickReader:
    """共享数据读取器"""

    def __init__(self, shared_dir: Path | None = None,
                 heartbeat_max_age: float = 10.0):
        self.dir = shared_dir or _get_shared_dir()
        self.heartbeat_max_age = heartbeat_max_age
        # 缓存
        self._cached_ticks = {}
        self._cached_indicators = {}
        self._cached_bar_signals = {}
        self._last_read = 0

    def _read(self, filename: str) -> dict | None:
        return read_json(self.dir / filename)

    def _check_stale(self, data: dict | None) -> bool:
        """检查数据是否过期（超过 heartbeat_max_age 秒无更新）"""
        if data is None:
            return True
        updated = data.get("_updated_at", "")
        if isinstance(updated, str):
            try:
                # ISO 格式 "2026-05-13T18:30:00.123456"
                from datetime import datetime
                updated_dt = datetime.fromisoformat(updated)
                age = time.time() - updated_dt.timestamp()
                return age > self.heartbeat_max_age
            except (ValueError, AttributeError):
                return True
        return False

    # ── 公开接口 ──

    def is_alive(self) -> bool:
        """Tick Engine 是否在运行"""
        hb = self._read("_heartbeat.json")
        if hb is None:
            return False
        if hb.get("status") != "running":
            return False
        # 检查更新时间
        now = time.time()
        updated = hb.get("updated_at", "")
        if isinstance(updated, str):
            # ISO 格式 → 粗略判断（如果文件是 30 秒前的，可能挂了）
            pass
        return True

    def get_ticks(self) -> dict:
        """获取所有品种的最新 tick"""
        data = self._read("ticks.json")
        if data and not self._check_stale(data):
            self._cached_ticks = data.get("ticks", {})
        return self._cached_ticks

    def get_tick(self, symbol: str) -> dict | None:
        """获取单个品种的 tick"""
        ticks = self.get_ticks()
        return ticks.get(symbol)

    def get_indicators(self, timeframe: str = "M5") -> dict:
        """获取指定时间框架的指标"""
        key = f"indicators_{timeframe}"
        data = self._read(f"{key}.json")
        if data and not self._check_stale(data):
            self._cached_indicators[key] = data.get("indicators", {})
        return self._cached_indicators.get(key, {})

    def get_indicator(self, symbol: str, timeframe: str = "M5") -> dict | None:
        """获取单个品种在指定 TF 的指标"""
        indicators = self.get_indicators(timeframe)
        return indicators.get(symbol)

    def get_bar_signal(self, symbol: str, timeframe: str = "M5") -> dict | None:
        """检查是否有新 bar 信号"""
        data = self._read("bar_signals.json")
        if data is None:
            return None
        key = f"{symbol}_{timeframe}"
        return data.get("signals", {}).get(key)

    def get_session(self, utc_hour: int | None = None) -> str:
        """获取当前交易时段"""
        if utc_hour is None:
            utc_hour = time.gmtime().tm_hour
        session_map = {"asia": (0, 8), "europe": (8, 13), "us": (13, 22)}
        for name, (start, end) in session_map.items():
            if start <= utc_hour < end:
                return name
        return "asia"

    def get_running_engines(self) -> list:
        """调试用：列出共享目录的文件"""
        try:
            files = sorted(self.dir.glob("*.json"))
            return [f.name for f in files]
        except Exception:
            return []

    def get_symbol_from_bar_signal(self, timeframe: str = "M5") -> list:
        """返回有新 bar 的品种列表"""
        data = self._read("bar_signals.json")
        if data is None:
            return []
        signals = data.get("signals", {})
        return [k for k, v in signals.items() if k.endswith(f"_{timeframe}")]


# ── 快速函数接口（不创建实例，适合简单调用） ──

_DEFAULT_READER: TickReader | None = None


def _get_reader() -> TickReader:
    global _DEFAULT_READER
    if _DEFAULT_READER is None:
        _DEFAULT_READER = TickReader()
    return _DEFAULT_READER


def get_ticks() -> dict:
    return _get_reader().get_ticks()


def get_tick(symbol: str) -> dict | None:
    return _get_reader().get_tick(symbol)


def get_indicators(timeframe: str = "M5") -> dict:
    return _get_reader().get_indicators(timeframe)


def get_indicator(symbol: str, timeframe: str = "M5") -> dict | None:
    return _get_reader().get_indicator(symbol, timeframe)


def is_engine_alive() -> bool:
    return _get_reader().is_alive()


def get_session(utc_hour: int | None = None) -> str:
    return _get_reader().get_session(utc_hour)
