SELECT
    f.numero_processo,
    t.sigla_tribunal,
    o.nome_orgao,
    c.nome_classe,
    f.dias_desde_ultimo_movimento,
    f.dias_desde_ajuizamento
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_tribunais t
    ON f.fk_tribunal = t.sk_tribunal
JOIN judicial.gold.dim_orgaos o
    ON f.fk_orgao = o.sk_orgao
JOIN judicial.gold.dim_classes c
    ON f.fk_classe = c.sk_classe
WHERE f.is_ultimo_movimento = true
    AND f.dias_desde_ultimo_movimento > 365
ORDER BY f.dias_desde_ultimo_movimento DESC