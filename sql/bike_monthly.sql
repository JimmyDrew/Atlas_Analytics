SELECT substr(dteday,1,7) AS month, SUM(cnt) AS rentals, COUNT(*) AS observed_hours
FROM bike GROUP BY month ORDER BY month;