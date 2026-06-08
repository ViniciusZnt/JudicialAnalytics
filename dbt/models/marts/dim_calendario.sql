-- models/marts/dim_calendario.sql
-- Gerada programaticamente — não vem de nenhuma fonte de dados.
-- sequence() produz um array com todos os dias de 2020 até hoje;
-- explode() transforma esse array em uma linha por dia.

select
    cast(date_format(data, 'yyyyMMdd') as int)           as sk_data,
    data,
    year(data)                                            as ano,
    month(data)                                           as mes,
    date_format(data, 'MMMM')                            as nome_mes,
    quarter(data)                                         as trimestre,
    case when month(data) <= 6 then 1 else 2 end          as semestre,
    date_format(data, 'EEEE')                            as dia_semana,
    dayofweek(data) in (1, 7)                             as is_fim_de_semana,
    false                                                 as is_feriado_nacional
from (
    select explode(sequence(date('2020-01-01'), current_date(), interval 1 day)) as data
)
