SELECT hr, workingday, COUNT(*) AS observed_hours, AVG(cnt) AS mean_rentals
FROM bike GROUP BY hr, workingday ORDER BY hr, workingday;