WITH weekly_data AS (
    SELECT
        WEEKOFYEAR(cal.data) AS semana,
        cal.ano,
        COUNT(*) AS total_movimentos
    FROM judicial.gold.fato_movimentos f
    JOIN judicial.gold.dim_calendario cal
        ON f.fk_data_movimento = cal.sk_data
    GROUP BY cal.ano, WEEKOFYEAR(cal.data)
),
new_processes AS (
    SELECT
        WEEKOFYEAR(cal_aj.data) AS semana,
        cal_aj.ano,
        COUNT(DISTINCT f.numero_processo) AS novos_processos
    FROM judicial.gold.fato_movimentos f
    JOIN judicial.gold.dim_calendario cal_aj
        ON f.fk_data_ajuizamento = cal_aj.sk_data
    GROUP BY cal_aj.ano, WEEKOFYEAR(cal_aj.data)
)
SELECT
    w.ano,
    w.semana,
    CONCAT(CAST(w.ano AS STRING), '-W', LPAD(CAST(w.semana AS STRING), 2, '0')) AS ano_semana,
    COALESCE(n.novos_processos, 0) AS novos_processos,
    w.total_movimentos
FROM weekly_data w
LEFT JOIN new_processes n
    ON w.ano = n.ano AND w.semana = n.semana
ORDER BY w.ano, w.semana