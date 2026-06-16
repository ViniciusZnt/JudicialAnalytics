SELECT
    COUNT(DISTINCT numero_processo)                         AS total_processos,
    COUNT(*)                                                AS total_movimentos,
    ROUND(AVG(dias_desde_ajuizamento), 0)                  AS tmp_medio,
    COUNT(DISTINCT CASE WHEN dias_desde_ultimo_movimento > 90
          AND is_ultimo_movimento THEN numero_processo END) AS processos_parados
FROM judicial.gold.fato_movimentos