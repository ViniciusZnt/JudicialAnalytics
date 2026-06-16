SELECT
    t.sigla_tribunal,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento BETWEEN 0 AND 29 THEN f.numero_processo END) AS `30d`,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento BETWEEN 30 AND 59 THEN f.numero_processo END) AS `60d`,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento BETWEEN 60 AND 89 THEN f.numero_processo END) AS `90d`,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento BETWEEN 90 AND 179 THEN f.numero_processo END) AS `180d`,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento >= 180 AND f.dias_desde_ultimo_movimento < 365 THEN f.numero_processo END) AS `180_365d`,
    COUNT(DISTINCT CASE WHEN f.dias_desde_ultimo_movimento >= 365 THEN f.numero_processo END) AS `365d_plus`
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_tribunais t
    ON f.fk_tribunal = t.sk_tribunal
WHERE f.is_ultimo_movimento = true
GROUP BY t.sigla_tribunal