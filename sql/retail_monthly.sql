SELECT substr(InvoiceDate,1,7) AS month,
 SUM(CASE WHEN category='sale' THEN value ELSE 0 END) AS gross_gbp,
 -SUM(CASE WHEN category='credit' THEN value ELSE 0 END) AS credits_gbp,
 SUM(CASE WHEN category IN ('sale','credit') THEN value ELSE 0 END) AS net_gbp,
 COUNT(DISTINCT CASE WHEN category='sale' THEN InvoiceNo END) AS orders
FROM retail GROUP BY month ORDER BY month;