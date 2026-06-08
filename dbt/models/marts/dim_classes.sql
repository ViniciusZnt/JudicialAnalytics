-- models/marts/dim_classes.sql
-- Classes processuais CNJ (ex: "Embargos à Execução", "Ação Civil Pública").
-- Surrogate key gerada sobre o código numérico.

select
    {{ dbt_utils.generate_surrogate_key(['codigo_classe']) }} as sk_classe,
    codigo_classe,
    nome_classe
from (
    select distinct codigo_classe, nome_classe
    from {{ source('silver', 'movimentos') }}
    where codigo_classe is not null
)
