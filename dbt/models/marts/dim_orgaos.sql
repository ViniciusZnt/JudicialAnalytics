-- Órgãos julgadores (varas, câmaras).
-- Referencia dim_tribunais via ref() — o dbt detecta essa dependência
-- e garante que dim_tribunais é materializada antes.

with orgaos as (
    select
        codigo_orgao,
        min(nome_orgao) as nome_orgao,
        sigla_tribunal
    from {{ source('silver', 'movimentos') }}
    where codigo_orgao is not null
    group by codigo_orgao, sigla_tribunal
)
select
    {{ dbt_utils.generate_surrogate_key(['o.codigo_orgao', 'o.sigla_tribunal']) }} as sk_orgao,
    o.codigo_orgao,
    o.nome_orgao,
    t.sk_tribunal as fk_tribunal
from orgaos o
left join {{ ref('dim_tribunais') }} t using (sigla_tribunal)