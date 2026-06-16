SELECT
    cal.mes,
    cal.nome_mes,
    COUNT(*) AS total_movimentos
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_calendario cal
    ON f.fk_data_movimento = cal.sk_data
GROUP BY cal.mes, cal.nome_mes
ORDER BY cal.mes