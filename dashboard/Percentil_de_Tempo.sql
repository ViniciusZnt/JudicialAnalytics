SELECT
    t.sigla_tribunal,
    ROUND(PERCENTILE(f.dias_desde_ajuizamento, 0.25), 0)   AS p25_dias,
    ROUND(PERCENTILE(f.dias_desde_ajuizamento, 0.50), 0)   AS p50_dias,
    ROUND(PERCENTILE(f.dias_desde_ajuizamento, 0.75), 0)   AS p75_dias,
    ROUND(PERCENTILE(f.dias_desde_ajuizamento, 0.90), 0)   AS p90_dias,
    ROUND(PERCENTILE(f.dias_desde_ajuizamento, 0.95), 0)   AS p95_dias,
    ROUND(AVG(f.dias_desde_ajuizamento), 0)                 AS media_dias
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_tribunais t ON f.fk_tribunal = t.sk_tribunal
WHERE f.is_ultimo_movimento = true
GROUP BY t.sigla_tribunal
ORDER BY media_dias DESC