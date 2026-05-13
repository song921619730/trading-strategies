"""
run_candlestick.py — Candlestick Pattern Hypothesis Testing Runner

Usage:
    python3 run_candlestick.py
        [--pattern inside_bar]
        [--direction long]
        [--timeframe H1]
        [--symbols XAUUSDm,EURUSDm,US30m]
        [--hold 3,5,7,10,15,20]

Or import and use programmatically:
    from run_candlestick import run_pattern_test
    results = run_pattern_test("doji and rsi14 < 40", direction="long")

Extends the existing grid_engine by adding candlestick feature columns
before running the grid.
"""

import sys
import os
import argparse
import pandas as pd
from pprint import pprint

# Add the existing futures-intraday scripts to path
SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "futures-intraday", "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Also add our own scripts dir
OUR_DIR = os.path.dirname(os.path.abspath(__file__))
if OUR_DIR not in sys.path:
    sys.path.insert(0, OUR_DIR)

from data_loader import load_data, compute_indicators, list_available_symbols
from candlestick_engine import run_candlestick_grid
from candlestick_features import add_candlestick_features, list_available_patterns, pattern_summary


# ─── Candlestick column names that need backtick-quoting in eval() ───
_CANDLESTICK_COLS = set(list_available_patterns())


def _quote_candlestick_cols(condition: str) -> str:
    """Wrap candlestick pattern column names in backticks for pandas eval().

    Column names like ``inside_bar`` contain underscores which pandas eval()
    interprets as subtraction. Backtick-quoting prevents that.
    """
    import re
    # Sort by length descending to match longer names first (avoid partial matches)
    sorted_cols = sorted(_CANDLESTICK_COLS, key=len, reverse=True)
    # Build a regex that matches whole words only
    pattern = r'\b(' + '|'.join(re.escape(c) for c in sorted_cols) + r')\b'
    return re.sub(pattern, r'`\1`', condition)


def prepare_data(timeframe: str = "H1", symbols: list = None) -> dict:
    """Load data and add candlestick features. Returns dict[symbol] -> df."""
    data = load_data(timeframe=timeframe, symbols=symbols)
    for sym in data:
        df = data[sym]
        df = compute_indicators(df)
        df = add_candlestick_features(df)
        data[sym] = df
    return data


def run_pattern_test(
    entry_condition: str,
    direction: str = "long",
    timeframe: str = "H1",
    symbols: list = None,
    hold_periods: list = None,
    verbose: bool = True,
) -> dict:
    """Run a candlestick pattern hypothesis through the grid engine.

    Args:
        entry_condition: Pandas eval string referencing candlestick feature columns.
                         E.g. "inside_bar and rsi14 < 40"
        direction: "long" or "short"
        timeframe: "H1" or "M30"
        symbols: List of symbols. None = all 14.
        hold_periods: List of hold periods. Default [3, 5, 7, 10, 15, 20].

    Returns:
        Grid engine results dict.
    """
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 12, 15, 20]
    if symbols is None:
        symbols = list_available_symbols(timeframe=timeframe)

    data = prepare_data(timeframe=timeframe, symbols=symbols)

    # Print pattern frequency summary
    if verbose:
        for sym in sorted(data.keys()):
            pdf = pattern_summary(data[sym])
            print(f"\n  📊 {sym} — Candlestick Pattern Frequency ({timeframe})")
            print(f"  {'-'*55}")
            for pat, row in pdf.head(10).iterrows():
                print(f"  {pat:<25} {int(row['count']):>6}  ({row['pct']:.2f}%)")
            print(f"  {'-'*55}")

    # Run candlestick grid
    quoted_condition = _quote_candlestick_cols(entry_condition)
    config = {
        "timeframe": timeframe,
        "symbols": symbols,
        "entry_condition": quoted_condition,
        "direction": direction,
        "hold_periods": hold_periods,
        "exit_at_close": True,
    }

    print(f"\n{'='*72}")
    print(f"  🕯️  CANDLESTICK TEST RUN")
    print(f"  Condition: {entry_condition}")
    print(f"  Quoted:    {quoted_condition}")
    print(f"  Direction: {direction} | TF: {timeframe}")
    print(f"  Symbols: {len(symbols)} | Holds: {hold_periods}")
    print(f"{'='*72}")

    results = run_candlestick_grid(config)

    # Pretty-print results
    meta = results.pop("_meta", {})
    print(f"\n  Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
    print()

    hits = []
    for sym in sorted(results.keys()):
        sym_res = results[sym]
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt == 0:
                continue
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            sharpe = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            label = "⭐" if wr >= 0.60 else ("👍" if wr >= 0.55 else "")
            print(f"  {label} {sym:<12} hold={hp:>2}  n={cnt:>5}  wr={wr:>6.2%}  "
                  f"avg={avg:>+8.4f}  sharpe={sharpe:>6.2f}  dd={dd:>7.4f}")
            if wr >= 0.55:
                hits.append((sym, hp, wr, cnt, sharpe, entry_condition, direction))

    results["_meta"] = meta

    # Summary
    if verbose and hits:
        print(f"\n  {'='*72}")
        print(f"  📈  HITS (wr >= 55%)")
        print(f"  {'='*72}")
        for sym, hp, wr, cnt, sharpe, cond, dir_ in sorted(hits, key=lambda x: -x[2]):
            print(f"  {sym:<12} hold={hp:>2}  wr={wr:>6.2%}  n={cnt:>5}  sharpe={sharpe:>6.2f}  "
                  f"dir={dir_:<5}  cond=\"{cond}\"")

    return results


def main():
    parser = argparse.ArgumentParser(description="Candlestick Pattern Hypothesis Tester")
    parser.add_argument("--pattern", type=str, default=None,
                        help="Candlestick pattern column to test (e.g. inside_bar, doji)")
    parser.add_argument("--condition", type=str, default=None,
                        help="Full entry condition (overrides --pattern + defaults)")
    parser.add_argument("--direction", type=str, default="long", choices=["long", "short"])
    parser.add_argument("--timeframe", type=str, default="H1", choices=["H1", "M30"])
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbols (default: all 14)")
    parser.add_argument("--hold", type=str, default="1,2,3,5,7,10,12,15,20",
                        help="Comma-separated hold periods")
    parser.add_argument("--list-patterns", action="store_true",
                        help="List all available candlestick patterns and exit")

    args = parser.parse_args()

    if args.list_patterns:
        print("Available candlestick patterns:")
        for p in list_available_patterns():
            print(f"  - {p}")
        return

    symbols = args.symbols.split(",") if args.symbols else None
    hold_periods = [int(x) for x in args.hold.split(",")]

    if args.condition:
        entry_condition = args.condition
    elif args.pattern:
        # Build a default entry_condition for this pattern
        entry_condition = args.pattern
    else:
        print("Specify --pattern or --condition. Use --list-patterns to see options.")
        sys.exit(1)

    run_pattern_test(
        entry_condition=entry_condition,
        direction=args.direction,
        timeframe=args.timeframe,
        symbols=symbols,
        hold_periods=hold_periods,
    )


if __name__ == "__main__":
    main()
