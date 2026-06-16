SELECT
    t.sigla_tribunal,
    COUNT(DISTINCT f.numero_processo) AS total_processos,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento > 90 THEN f.numero_processo END) AS processos_parados
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_tribunais t
    ON f.fk_tribunal = t.sk_tribunal
WHERE f.is_ultimo_movimento = true
GROUP BY t.sigla_tribunal