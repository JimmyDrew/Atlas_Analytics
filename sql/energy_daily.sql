SELECT substr(date,1,10) AS day, COUNT(*) AS observations,
 SUM(Appliances)/1000.0 AS appliance_kwh,
 SUM(lights)/1000.0 AS lighting_kwh
FROM energy GROUP BY day ORDER BY day;