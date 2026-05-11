-- DLR 模板 02：板块聚类分析
-- 用途：分析涨停股票所属概念/行业板块分布，找出热点板块
-- 输入：limit_pool 查询结果中的 ts_code 列表
-- 输出：按涨停数排序的板块分布

SELECT
    c.concept_name,
    count(*) as limit_count,
    groupArray(l.ts_code) as stocks,
    avg(l.limit_times) as avg_limit_times,
    avg(l.fc_ratio) as avg_fc_ratio
FROM tushare.tushare_concept_detail c FINAL
JOIN tushare.tushare_limit_list_d l FINAL
  ON c.ts_code = l.ts_code
WHERE l.trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
  AND l.limit_times > 0
  AND c.concept_name IS NOT NULL
  AND c.concept_name != ''
GROUP BY c.concept_name
ORDER BY limit_count DESC
LIMIT 30
