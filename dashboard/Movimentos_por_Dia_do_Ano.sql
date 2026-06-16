SELECT
    cal.data,
    DAYOFYEAR(cal.data) AS dia_ano,
    cal.dia_semana,
    CASE cal.dia_semana
        WHEN 'Monday' THEN 1
        WHEN 'Tuesday' THEN 2
        WHEN 'Wednesday' THEN 3
        WHEN 'Thursday' THEN 4
        WHEN 'Friday' THEN 5
        WHEN 'Saturday' THEN 6
        WHEN 'Sunday' THEN 7
    END AS dia_semana_ordem,
    cal.mes,
    cal.ano,
    COUNT(*) AS total_movimentos
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_calendario cal
    ON f.fk_data_movimento = cal.sk_data
GROUP BY cal.data, cal.dia_semana, cal.mes, cal.ano
ORDER BY dia_semana_ordem, dia_ano