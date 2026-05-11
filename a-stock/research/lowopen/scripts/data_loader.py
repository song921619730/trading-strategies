import pandas as pd
import requests
from typing import List, Dict, Any, Optional
import io

# ============================================================
# A 股 Kanban Loop - 数据加载器 (Data Loader) v4 (Requests)
# ============================================================
# 核心职责：
# 1. 连接 ClickHouse HTTP 接口 (172.24.224.1:8123)
# 2. 根据 config 动态拼接 SQL (JOIN 多表)
# 3. 返回对齐后的 DataFrame

# 表名映射：简化名 -> 实际 ClickHouse 表名
TABLE_MAP = {
    "daily": "tushare_stock_daily",
    "daily_basic": "tushare_daily_basic",
    "moneyflow": "tushare_moneyflow",
    "limit_list": "tushare_limit_list_d",
    "index_daily": "tushare_index_daily",
    "daily_basic_hsgt": "tushare_moneyflow_hsgt",
    "concept_cons": "tushare_kpl_concept_cons",
}

# 每张表的可用字段（防幻觉）
TABLE_FIELDS = {
    "daily": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"],
    "daily_basic": ["turnover_rate", "turnover_rate_f", "volume_ratio", "pe", "pe_ttm", "pb", "ps", "total_mv", "circ_mv", "float_share", "total_share"],
    "moneyflow": ["buy_sm_vol", "sell_sm_vol", "buy_md_vol", "sell_md_vol", "buy_lg_vol", "sell_lg_vol", "buy_elg_vol", "sell_elg_vol", "net_mf_vol"],
    "limit_list": ["limit", "limit_times", "first_time", "last_time"],
}


class DataLoader:
    def __init__(self, host: str = "172.24.224.1", port: int = 8123,
                 user: str = "ai_reader", password: str = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ",
                 database: str = "tushare"):
        self.url = f"http://{host}:{port}/"
        self.params = {
            "user": user,
            "password": password,
            "database": database,
            "default_format": "TabSeparatedWithNames"
        }

    def get_date_range(self) -> tuple[str, str]:
        """动态获取数据库中的最大最小交易日期"""
        sql = "SELECT min(trade_date), max(trade_date) FROM tushare_stock_daily FINAL"
        df = self.query_df(sql)
        if not df.empty:
            return str(df.iloc[0, 0]), str(df.iloc[0, 1])
        return "2000-01-01", "2026-01-01"

    def query_df(self, sql: str) -> pd.DataFrame:
        """执行 SQL 查询并返回 DataFrame"""
        try:
            response = requests.post(self.url, params=self.params, data=sql.encode('utf-8'))
            response.raise_for_status()
            
            if not response.text.strip():
                return pd.DataFrame()
                
            df = pd.read_csv(io.StringIO(response.text), sep='\t')
            return df
        except Exception as e:
            print(f" ClickHouse Query Error: {e}")
            print(f"SQL: {sql[:300]}...")
            return pd.DataFrame()

    def load_data(self, tables: List[str], start_date: str, end_date: str,
                  ts_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """
        动态加载并 JOIN 多张表。
        """
        print(f"Loading data for {len(tables)} tables from {start_date} to {end_date}...")

        base_simple = "daily"
        base_table = TABLE_MAP.get(base_simple, base_simple)
        base_fields = TABLE_FIELDS.get(base_simple, ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg"])
        # 构建 SQL
        # 基表字段不用别名前缀（保持列名简洁）
        select_fields = [f"t1.{f} as {f}" for f in base_fields]
        joins = []

        for i, table in enumerate(tables):
            if table == base_simple:
                continue

            actual_name = TABLE_MAP.get(table, table)
            alias = f"t{i+2}"
            fields = TABLE_FIELDS.get(table, [])

            if not fields:
                print(f"  Unknown table '{table}', skipping fields.")
                continue

            for f in fields:
                select_fields.append(f"{alias}.{f}")

            joins.append(
                f"LEFT JOIN (SELECT * FROM {actual_name} FINAL) {alias} "
                f"ON t1.ts_code = {alias}.ts_code AND t1.trade_date = {alias}.trade_date"
            )

        where_clauses = [
            f"t1.trade_date >= '{start_date}'",
            f"t1.trade_date <= '{end_date}'",
        ]
        if ts_codes:
            code_str = "','".join(ts_codes)
            where_clauses.append(f"t1.ts_code IN ('{code_str}')")

        sql = f"""
        SELECT {', '.join(select_fields)}
        FROM {base_table} AS t1 FINAL
        {' '.join(joins)}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY t1.ts_code, t1.trade_date
        """

        print(f"  SQL length: {len(sql)} chars")
        
        df = self.query_df(sql)
        print(f"  Loaded {len(df)} rows, {len(df.columns)} columns.")
        
        return df


if __name__ == '__main__':
    loader = DataLoader()
    df = loader.load_data(
        tables=['daily', 'daily_basic'],
        start_date='2026-04-01',
        end_date='2026-05-08',
        ts_codes=['000001.SZ', '600519.SH']
    )
    print(f"\nShape: {df.shape}")
    if not df.empty:
        print(f"\nFirst 5 rows:")
        print(df.head())
