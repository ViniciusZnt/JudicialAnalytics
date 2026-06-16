SELECT
    t.sigla_tribunal,
    o.nome_orgao,
    COUNT(DISTINCT f.numero_processo)                       AS processos_parados,
    ROUND(AVG(f.dias_desde_ultimo_movimento), 0)            AS media_inatividade
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_tribunais t ON f.fk_tribunal = t.sk_tribunal
JOIN judicial.gold.dim_orgaos    o ON f.fk_orgao    = o.sk_orgao
WHERE f.is_ultimo_movimento = true
  AND f.dias_desde_ultimo_movimento > 90
GROUP BY t.sigla_tribunal, o.nome_orgao
ORDER BY processos_parados DESC
LIMIT 20