#!/usr/bin/env python3
"""data_loader.py — High-RR 数据加载器

使用预计算的增强 parquet 文件（含全部技术指标列）。
不重复计算指标，只做加载和元数据查询。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger("high_rr_data_loader")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# 全部 19 个 MT5 品种
_SCRIPTS = str(SCRIPT_DIR.parent.parent.parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from mt5_symbols import MT5_SYMBOLS_19
SYMBOLS = MT5_SYMBOLS_19

TIMEFRAME_DIRS = {
    "H1": DATA_DIR / "H1",
    "M5": DATA_DIR / "M5",
    "M15": DATA_DIR / "M15",
}

# 预计算文件后缀
ENHANCED_SUFFIX = "_enhanced.parquet"


def list_available_symbols(timeframe: str = "M5") -> List[str]:
    """列出指定时间框架下已预计算的品种"""
    d = TIMEFRAME_DIRS.get(timeframe)
    if not d or not d.exists():
        return []
    return sorted([p.stem.replace("_enhanced", "") for p in d.glob(f"*{ENHANCED_SUFFIX}")])


def load_data(timeframe: str = "M5", symbols: Optional[List[str]] = None,
              start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """加载预计算增强数据（直接读取含全部指标的 _enhanced.parquet）

    不需要额外 compute_indicators，所有列已预计算好。
    """
    d = TIMEFRAME_DIRS.get(timeframe)
    if not d or not d.exists():
        log.warning("Data directory not found: %s", d)
        return {}

    if symbols is None:
        symbols = list_available_symbols(timeframe)

    result = {}
    for sym in symbols:
        fp = d / f"{sym}{ENHANCED_SUFFIX}"
        if not fp.exists():
            # Fallback: 尝试原始 parquet（无指标）
            fp = d / f"{sym}.parquet"
            if not fp.exists():
                log.warning("Missing data: %s (neither enhanced nor raw)", sym)
                continue

        try:
            df = pd.read_parquet(fp)
        except Exception as e:
            log.error("Failed to read %s: %s", fp, e)
            continue

        if df.empty:
            continue

        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            else:
                log.warning("No time index for %s", sym)
                continue

        df = df.sort_index()
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]

        result[sym] = df
        log.info("Loaded %s %s: %d rows x %d cols [%s → %s]",
                 sym, timeframe, len(df), len(df.columns),
                 df.index[0].strftime("%Y-%m-%d %H:%M"),
                 df.index[-1].strftime("%Y-%m-%d %H:%M"))

    return result


def detect_h1_trend(h1_df: pd.DataFrame) -> str:
    """判断 H1 趋势方向（使用预计算列）

    返回 'up', 'down', 'sideways'
    """
    if h1_df.empty or len(h1_df) < 5:
        return "sideways"

    last = h1_df.iloc[-1]

    # 使用预计算的 ema12_above_ema26 和 market_regime
    ema_bullish = last.get("ema12_above_ema26", 0) == 1
    market_regime = last.get("market_regime", "sideways")

    # 额外检查 HH 结构
    hh_20 = last.get("hh_20", 0)
    ll_20 = last.get("ll_20", 0)
    close = last["close"]

    if ema_bullish and market_regime == "bull":
        # 确认 HH 在抬高
        if len(h1_df) >= 20:
            mid_hh = h1_df.iloc[-10:-5]["hh_20"].max()
            if hh_20 >= mid_hh:
                return "up"
        return "up"
    elif not ema_bullish and market_regime == "bear":
        if len(h1_df) >= 20:
            mid_ll = h1_df.iloc[-10:-5]["ll_20"].min()
            if ll_20 <= mid_ll:
                return "down"
        return "down"
    else:
        return "sideways"


def detect_pullback_to_ma(m5_last: pd.Series, h1_ma50: float) -> bool:
    """检测 M5 是否回调到 H1 MA50 附近（±0.5 ATR）"""
    atr = m5_last.get("atr14", 0)
    if atr <= 0:
        return False
    return abs(m5_last["close"] - h1_ma50) <= atr * 0.5


def get_data_info() -> dict:
    """返回数据状态摘要"""
    info = {}
    for tf in ["H1", "M5"]:
        d = TIMEFRAME_DIRS.get(tf)
        if not d or not d.exists():
            info[tf] = {"symbols": 0, "rows": 0, "cols": 0}
            continue
        files = list(d.glob(f"*{ENHANCED_SUFFIX}"))
        symbols = len(files)
        info[tf] = {
            "symbols": symbols,
            "columns": None,
        }
        if files:
            try:
                df = pd.read_parquet(files[0])
                info[tf]["columns"] = len(df.columns)
                info[tf]["rows"] = len(df)
            except:
                pass
    return info
