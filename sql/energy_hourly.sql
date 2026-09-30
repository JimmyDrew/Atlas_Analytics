SELECT CAST(substr(date,12,2) AS INTEGER) AS hour,
 COUNT(*) AS observations, AVG(Appliances) AS mean_wh
FROM energy GROUP BY hour ORDER BY hour;