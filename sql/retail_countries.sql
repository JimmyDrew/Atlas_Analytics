SELECT Country, SUM(value) AS gross_gbp FROM retail
WHERE category='sale' GROUP BY Country ORDER BY gross_gbp DESC LIMIT 10;