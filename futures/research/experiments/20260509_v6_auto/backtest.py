#!/usr/bin/env python3
"""
Backtest Template for Strategy Research
AI 研究员可在此模板基础上填充具体逻辑。
"""

import pandas as pd
import numpy as np

def load_data(path):
    """加载行情数据"""
    df = pd.read_csv(path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    return df

def calculate_signals(df):
    """
    AI 在此处编写信号生成逻辑
    返回: signals DataFrame
    """
    # TODO: 添加自定义因子计算
    signals = pd.DataFrame(index=df.index)
    return signals

def run_backtest(df, signals):
    """
    AI 在此处编写回测引擎
    返回: 绩效指标字典
    """
    # TODO: 实现资金曲线、回撤、夏普计算
    return {"return": 0.0, "max_dd": 0.0, "sharpe": 0.0}

if __name__ == "__main__":
    print("Backtest Template Ready. AI will fill in the logic.")
