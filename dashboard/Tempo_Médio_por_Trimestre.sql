SELECT
    cal.ano,
    cal.trimestre,
    CONCAT(cal.ano, '-Q', cal.trimestre) AS ano_trimestre,
    ROUND(AVG(f.dias_desde_ajuizamento), 0) AS tmp_medio
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_calendario cal
    ON f.fk_data_movimento = cal.sk_data
WHERE f.is_ultimo_movimento = true
GROUP BY cal.ano, cal.trimestre
ORDER BY cal.ano, cal.trimestre