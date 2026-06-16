SELECT
    c.nome_classe,
    cal.ano,
    cal.mes,
    CONCAT(cal.ano, '-', LPAD(cal.mes, 2, '0')) AS ano_mes,
    COUNT(DISTINCT f.numero_processo) AS total_processos,
    ROUND(AVG(f.dias_desde_ajuizamento), 0) AS tmp_medio
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_classes c
    ON f.fk_classe = c.sk_classe
JOIN judicial.gold.dim_calendario cal
    ON f.fk_data_movimento = cal.sk_data
WHERE f.is_ultimo_movimento = true
GROUP BY c.nome_classe, cal.ano, cal.mes
ORDER BY cal.ano, cal.mes, total_processos DESC