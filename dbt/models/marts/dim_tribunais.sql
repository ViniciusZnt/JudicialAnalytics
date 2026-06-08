-- models/marts/dim_tribunais.sql
-- Uma linha por tribunal.
-- Surrogate key gerada com sha2 sobre a sigla.
-- Por que surrogate key e não a sigla diretamente como PK?
-- A chave natural pode mudar ou ter variações entre fontes.
-- A SK é estável: mesmo que a sigla mude, as FKs na fato não precisam ser reescritas.

select
    {{ dbt_utils.generate_surrogate_key(['sigla_tribunal']) }} as sk_tribunal,
    sigla_tribunal
from (
    select distinct sigla_tribunal
    from {{ source('silver', 'movimentos') }}
    where sigla_tribunal is not null
)
