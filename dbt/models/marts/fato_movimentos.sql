-- models/marts/fato_movimentos.sql
-- Cada linha é um evento processual (movimento).
-- Armazena apenas FKs e métricas — nenhum atributo descritivo.
-- Para saber o nome do tribunal, faça JOIN com dim_tribunais.
--
-- FKs para datas: calculadas com date_format(..., 'yyyyMMdd') — mesmo formato
-- do dim_calendario.sk_data, sem o custo de um JOIN extra.
--
-- tipo_fase: mapeamento de codigo_movimento para fase analítica,
-- conforme tabela CNJ de movimentos (ranges de código por fase).
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['numero_processo', 'codigo_movimento', 'data_movimento'],
        file_format='delta'
    )
}}

select
    m.numero_processo,
    m.data_movimento,                                                           -- ← ancoragem incremental
    t.sk_tribunal                                                               as fk_tribunal,
    c.sk_classe                                                                 as fk_classe,
    o.sk_orgao                                                                  as fk_orgao,
    cast(date_format(cast(m.data_movimento   as date), 'yyyyMMdd') as int)     as fk_data_movimento,
    cast(date_format(cast(m.data_ajuizamento as date), 'yyyyMMdd') as int)     as fk_data_ajuizamento,
    m.codigo_movimento,
    m.grau,
    case
        when m.codigo_movimento between 1   and 99  then 'distribuição'
        when m.codigo_movimento between 100 and 199 then 'conhecimento'
        when m.codigo_movimento between 200 and 299 then 'instrução'
        when m.codigo_movimento between 300 and 399 then 'sentença'
        when m.codigo_movimento between 400 and 499 then 'recurso'
        when m.codigo_movimento between 500 and 599 then 'execução'
        when m.codigo_movimento between 600 and 699 then 'arquivamento'
        else 'outro'
    end                                                                         as tipo_fase,
    m.dias_desde_ajuizamento,
    m.dias_desde_ultimo_movimento,
    m.is_ultimo_movimento

from {{ source('silver', 'movimentos') }} m
left join {{ ref('dim_tribunais') }} t using (sigla_tribunal)
left join {{ ref('dim_classes') }}   c using (codigo_classe)
left join {{ ref('dim_orgaos') }}    o using (codigo_orgao)

{% if is_incremental() %}
where m.data_movimento > (
    select max(dest.data_movimento)
    from {{ this }} dest
)
{% endif %}