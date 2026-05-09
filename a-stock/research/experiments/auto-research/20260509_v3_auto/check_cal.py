import requests
from io import StringIO
import pandas as pd

URL = 'http://172.24.224.1:8123/'
AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

r = requests.get(URL, params={'query': 'DESCRIBE TABLE tushare.tushare_trade_cal FORMAT TabSeparatedWithNames'}, auth=AUTH, timeout=30)
print("trade_cal 表结构:")
print(r.text)

r2 = requests.get(URL, params={'query': "SELECT * FROM tushare.tushare_trade_cal FINAL WHERE exchange='SSE' AND calendar_date >= '20260420' LIMIT 10 FORMAT TabSeparatedWithNames"}, auth=AUTH, timeout=30)
print("\n样例数据:")
print(r2.text)
