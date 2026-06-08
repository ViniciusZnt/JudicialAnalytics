-- models/marts/dim_orgaos.sql
-- Órgãos julgadores (varas, câmaras).
-- Referencia dim_tribunais via {{ ref() }} — o dbt detecta essa dependência
-- e garante que dim_tribunais é materializada antes.

select
    {{ dbt_utils.generate_surrogate_key(['m.codigo_orgao']) }} as sk_orgao,
    m.codigo_orgao,
    m.nome_orgao,
    t.sk_tribunal as fk_tribunal
from (
    select distinct codigo_orgao, nome_orgao, sigla_tribunal
    from {{ source('silver', 'movimentos') }}
    where codigo_orgao is not null
) m
left join {{ ref('dim_tribunais') }} t using (sigla_tribunal)
