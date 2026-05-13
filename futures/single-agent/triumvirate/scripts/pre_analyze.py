"""
Triumvirate — Pre-Analysis Engine (Magic 234004)

职责: 调用 CIO 的 pre_analyze.py 获取市场数据
日志: 每次扫描记录到 logs/scans/ + data/pre_analyze_latest.json
"""
import sys
import os
import json
import subprocess
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)
CIO_DIR = os.path.normpath(os.path.join(TRIUMVIRATE_DIR, "..", "pure-ai-cio"))
CIO_PRE_ANALYZE_SCRIPT = os.path.join(CIO_DIR, "scripts", "pre_analyze.py")


def log_json(data: dict, subdir: str, filename: str):
    """Save data to a log file"""
    log_dir = os.path.join(TRIUMVIRATE_DIR, "logs", subdir)
    os.makedirs(log_dir, exist_ok=True)
    filepath = os.path.join(log_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] Failed to write log: {e}", file=sys.stderr)


def main():
    # Determine Python executable
    if sys.platform == "win32":
        python_exe = r"C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe"
    else:
        python_exe = "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe"

    cmd = [python_exe, CIO_PRE_ANALYZE_SCRIPT]
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=CIO_DIR
        )

        if result.returncode != 0:
            error_data = {
                "timestamp": timestamp,
                "error": f"pre_analyze failed (exit={result.returncode})",
                "stderr": result.stderr,
            }
            print(json.dumps(error_data))
            log_json(error_data, "scans", f"{timestamp}_pre_analyze_ERROR.json")
            sys.exit(1)

        # Parse output
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            error_data = {
                "timestamp": timestamp,
                "error": "pre_analyze output is not valid JSON",
                "raw_stdout": result.stdout[:2000],
            }
            print(json.dumps(error_data))
            log_json(error_data, "scans", f"{timestamp}_pre_analyze_JSON_ERROR.json")
            sys.exit(1)

        # Inject scan metadata
        data["_meta"] = data.get("_meta", {})
        data["_meta"]["scan_timestamp"] = timestamp
        data["_meta"]["source"] = "CIO_pre_analyze"
        data["_meta"]["triumvirate_link"] = "Magic 234004"

        # ====== LOGGING ======

        # 1. Save to data/ (latest, overwrite) — for quick access
        data_dir = os.path.join(TRIUMVIRATE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "pre_analyze_latest.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 2. Save to logs/scans/ (timestamped, preserve history)
        log_json(data, "scans", f"{timestamp}_pre_analyze.json")

        # 3. Print to stdout for AI consumption
        print(json.dumps(data, indent=2))

    except subprocess.TimeoutExpired:
        error_data = {"timestamp": timestamp, "error": "pre_analyze timed out after 60s"}
        print(json.dumps(error_data))
        log_json(error_data, "scans", f"{timestamp}_pre_analyze_TIMEOUT.json")
        sys.exit(1)
    except FileNotFoundError:
        error_data = {"timestamp": timestamp, "error": f"Python executable not found: {python_exe}"}
        print(json.dumps(error_data))
        log_json(error_data, "scans", f"{timestamp}_pre_analyze_NO_PYTHON.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
