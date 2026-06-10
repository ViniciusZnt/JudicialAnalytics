-- models/marts/dim_assuntos.sql
-- Lê direto da Bronze porque a Silver só armazena movimentos explodidos.
-- Os assuntos ficam em _source.assuntos (array) e não foram propagados para a Silver.
-- LATERAL VIEW EXPLODE expande o array: uma linha por assunto por processo.

select
    {{ dbt_utils.generate_surrogate_key(['codigo_assunto']) }} as sk_assunto,
    codigo_assunto,
    nome_assunto
from {{ source('bronze', 'datajud_raw') }},
inline(
    transform(
        _source.assuntos,
        x -> from_json(x, 'struct<codigo:bigint,nome:string>')
    )
) as (codigo_assunto, nome_assunto)
where codigo_assunto is not null
group by 1, 2, 3
