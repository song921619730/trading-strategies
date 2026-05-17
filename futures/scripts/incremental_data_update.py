#!/usr/bin/env python3
"""
incremental_data_update.py — 增量更新期货研究数据

读取现有 parquet 数据找到最新时间戳，
仅从 MT5 下载该时间戳之后的新数据并追加。
"""
import os, sys, json
from datetime import datetime, timezone

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ── 配置 ──
SYMBOLS = ["XAUUSD","XAGUSD","EURUSD","GBPUSD","USDJPY",
           "AUDUSD","USDCHF","USOIL","UKOIL","USTEC",
           "US30","US500","JP225","HK50",
           "DXY","USDCAD","NZDUSD","XNGUSD","XCUUSD"]

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASETS = {
    "intraday": {
        "name": "期货日内 (全TF)",
        "data_dir": os.path.join(BASE, "research", "kanban", "futures-intraday", "data"),
        "timeframes": {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        },
    },
    "scalping": {
        "name": "超短线 (全TF)",
        "data_dir": os.path.join(BASE, "research", "kanban", "scalping-m1", "data"),
        "timeframes": {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        },
    },
    "high-rr": {
        "name": "高盈亏比 (全TF)",
        "data_dir": os.path.join(BASE, "research", "kanban", "high-rr-research", "data"),
        "timeframes": {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        },
    },
}


def get_latest_time(parquet_path):
    """读取 parquet 文件的最新时间戳；文件不存在则返回 None"""
    if not os.path.exists(parquet_path):
        return None
    df = pd.read_parquet(parquet_path)
    if len(df) == 0:
        return None
    return df.index.max()


def update_dataset(ds_config):
    """增量更新一个数据集的所有品种和周期"""
    name = ds_config["name"]
    data_dir = ds_config["data_dir"]
    timeframes = ds_config["timeframes"]

    print(f"\n{'='*60}")
    print(f"📦 {name}")
    print(f"{'='*60}")

    for tf_name, tf_const in timeframes.items():
        tf_dir = os.path.join(data_dir, tf_name)
        os.makedirs(tf_dir, exist_ok=True)

        print(f"\n  ⏱  {tf_name}")
        for sym in SYMBOLS:
            parquet_path = os.path.join(tf_dir, f"{sym}.parquet")
            latest = get_latest_time(parquet_path)

            # 确定起始时间
            if latest is not None:
                # 从最新一根 K 线之前开始，防止遗漏最后一根未确认
                start_from = latest - pd.Timedelta(hours=2)
                action = "增量"
            else:
                start_from = datetime(2021, 1, 1, tzinfo=timezone.utc)
                action = "全量"

            # 将 start_from 转成 datetime 对象
            if hasattr(start_from, 'to_pydatetime'):
                dt_start = start_from.to_pydatetime()
            else:
                dt_start = start_from

            print(f"    {sym:10s} [{action}] 从 {dt_start} 开始 ...", end=" ", flush=True)

            try:
                # 获取从 start_from 到现在的所有数据
                rates = mt5.copy_rates_from(sym, tf_const, datetime.now(timezone.utc), 50000)
                if rates is None or len(rates) == 0:
                    print(f"⚠️ 无数据 ({mt5.last_error()})")
                    continue

                new_df = pd.DataFrame(rates)
                new_df['time'] = pd.to_datetime(new_df['time'], unit='s')
                new_df.set_index('time', inplace=True)
                new_df = new_df[['open','high','low','close','tick_volume','spread','real_volume']]

                # 统一时区：如果现有数据有时区，给新数据也加上
                if latest is not None and latest.tz is not None:
                    if new_df.index.tz is None:
                        new_df.index = new_df.index.tz_localize('UTC')
                    else:
                        new_df.index = new_df.index.tz_convert('UTC')

                # 只保留起始时间之后的新数据
                cutoff = latest if latest is not None else pd.Timestamp.min
                if cutoff.tz is None and new_df.index.tz is not None:
                    cutoff = cutoff.tz_localize('UTC')
                elif cutoff.tz is not None and new_df.index.tz is None:
                    cutoff = cutoff.tz_localize(None)

                new_df = new_df[new_df.index > cutoff]

                if len(new_df) == 0:
                    print("✅ 已是最新")
                    continue

                print(f"+{len(new_df)} 根 K 线, 最新到 {new_df.index.max()}")

                if latest is not None and os.path.exists(parquet_path):
                    # 追加到现有数据
                    old_df = pd.read_parquet(parquet_path)
                    combined = pd.concat([old_df, new_df])
                    # 去重（保留最后一次出现的行）
                    combined = combined[~combined.index.duplicated(keep='last')]
                    combined.sort_index(inplace=True)
                    combined.to_parquet(parquet_path)
                else:
                    # 新文件
                    new_df.to_parquet(parquet_path)

            except Exception as e:
                print(f"❌ 失败: {e}")


def main():
    print(f"🕐 增量数据更新 — {datetime.now().isoformat()}")
    print(f"📡 品种数: {len(SYMBOLS)}")

    if not mt5.initialize():
        print(f"❌ MT5 初始化失败: {mt5.last_error()}")
        sys.exit(1)

    try:
        for key, cfg in DATASETS.items():
            update_dataset(cfg)
        print(f"\n{'='*60}")
        print("✅ 更新完成")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
