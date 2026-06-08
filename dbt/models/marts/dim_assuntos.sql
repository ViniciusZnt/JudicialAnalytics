-- models/marts/dim_assuntos.sql
-- Lê direto da Bronze porque a Silver só armazena movimentos explodidos.
-- Os assuntos ficam em _source.assuntos (array) e não foram propagados para a Silver.
-- LATERAL VIEW EXPLODE expande o array: uma linha por assunto por processo.

select
    {{ dbt_utils.generate_surrogate_key(['assunto.codigo']) }} as sk_assunto,
    assunto.codigo as codigo_assunto,
    assunto.nome   as nome_assunto
from {{ source('bronze', 'datajud_raw') }}
lateral view explode(_source.assuntos) t as assunto
where assunto.codigo is not null
group by 1, 2, 3
