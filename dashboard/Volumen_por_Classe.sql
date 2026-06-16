SELECT
    c.nome_classe,
    COUNT(DISTINCT f.numero_processo) AS total_processos,
    ROUND(AVG(f.dias_desde_ajuizamento), 0) AS tmp_medio,
    COUNT(*) AS total_movimentos
FROM judicial.gold.fato_movimentos f
JOIN judicial.gold.dim_classes c
    ON f.fk_classe = c.sk_classe
WHERE f.is_ultimo_movimento = true
GROUP BY c.nome_classe
ORDER BY total_processos DESC