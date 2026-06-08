# Judicial Analytics Platform

Plataforma analítica operacional do Judiciário brasileiro construída sobre dados públicos do CNJ.

Transforma eventos processuais brutos da API DataJud em métricas operacionais estruturadas — tempo médio de processamento, taxa de congestionamento e gargalos por fase — organizadas em uma arquitetura medalhão (Bronze → Silver → Gold) em nuvem.

## Stack

| Camada | Tecnologia | Responsabilidade |
|---|---|---|
| Ingestão | Python + boto3 (GitHub Actions) | Única camada com acesso à internet — pagina a API e grava no S3 |
| Storage | AWS S3 + Delta Lake (Unity Catalog) | Bronze, Silver e Gold em arquivos Delta |
| Transformação | dbt-databricks + SQL Warehouse | SQL puro, sem PySpark — menor custo de DBU |
| Orquestração | GitHub Actions → Databricks Jobs | Actions agenda e dispara; Jobs executa as tasks |
| Visualização | Databricks SQL Dashboards | Conecta direto nas tabelas Gold |

## Fontes de dados

- **DataJud (CNJ)** — API REST sobre Elasticsearch. Eventos processuais com paginação `search_after`. Campos-chave: `numeroProcesso`, `tribunal`, `dataAjuizamento`, `classeProcessual`, `movimentos[]`, `grau`.
- **Tabelas unificadas CNJ** — classes, assuntos e movimentos processuais (de/para dos códigos).

**Tribunais cobertos:** TJRS, TJSC, TJPR, TJSP — primeiro grau (G1).

## Pré-requisitos

- Python 3.13+ e [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Conta AWS com bucket S3 `judicial-analytics-storage`
- Workspace Databricks com Unity Catalog habilitado (catálogo `judicial`, schemas `bronze`/`silver`/`gold`)

## Como rodar

O pipeline é acionado pelo GitHub Actions. Vá em **Actions → Pipeline Judicial → Run workflow**, informe as datas de início e fim, e o workflow:

1. **Ingestão** — pagina a API DataJud e grava os JSONs no S3 (`bronze/raw_files/{tribunal}/`)
2. **Trigger** — dispara o Databricks Job, que executa em sequência:
   - `load_bronze` — lê os JSONs do S3, faz merge na tabela Delta Bronze e move os arquivos para `processados/`
   - `dbt run --select staging` — parsing, tipagem e explode dos movimentos (Silver)
   - `dbt run --select marts` — modelo estrela (Gold)
   - `dbt test` — se falhar, o Job para e o dashboard mantém os dados da execução anterior

### Execução local

```bash
uv sync                                      # instalar dependências
uv run dbt deps --project-dir dbt/           # instalar dbt-utils

uv run python -m ingestion.ingest_bronze     # só ingestão → S3
uv run dbt run  --project-dir dbt/           # só transformações (requer SQL Warehouse)
uv run dbt test --project-dir dbt/
```

## Configuração

Cadastre os secrets em **Settings → Secrets and variables → Actions**:

| Secret | Origem |
|---|---|
| `DATAJUD_API_KEY` | [datajud-wiki.cnj.jus.br](https://datajud-wiki.cnj.jus.br/) (gratuita) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM User com acesso ao bucket S3 |
| `AWS_DEFAULT_REGION` | Região do bucket (ex: `us-east-1`) |
| `DATABRICKS_HOST` | URL base do workspace (sem path `/browse?o=...`) |
| `DATABRICKS_TOKEN` | Settings → Developer → Access tokens |
| `DATABRICKS_JOB_ID` | ID do job criado no Databricks |

Edite [dbt/profiles.yml](dbt/profiles.yml) com o `host` e `http_path` do seu SQL Warehouse.

> Para testes locais sem o Actions, copie `.env.example` para `.env` (contém só `DATAJUD_API_KEY`) e exporte as variáveis AWS/Databricks no shell.

## Modelo de dados (Gold — `judicial.gold`)

Modelo estrela com surrogate keys via `dbt_utils.generate_surrogate_key`. A fato contém apenas FKs e métricas.

| Tabela | Materialização | Descrição |
|---|---|---|
| `dim_tribunais`, `dim_classes`, `dim_assuntos`, `dim_orgaos` | `table` | Dimensões descritivas |
| `dim_calendario` | `table` | Datas de 2020 até hoje |
| `fato_movimentos` | `incremental` (merge) | Um evento por linha |

Métricas em `fato_movimentos`: `dias_desde_ajuizamento`, `dias_desde_ultimo_movimento`, `is_ultimo_movimento`.

Testes dbt garantem qualidade: `not_null`/`unique` nas chaves, `relationships` entre fato e dimensões, e `dias_desde_ajuizamento >= 0`.

## Estrutura

```
ingestion/
  datajud_client.py          # cliente HTTP com paginação search_after
  ingest_bronze.py           # ingestão + watermark → S3
  trigger_databricks_job.py  # POST /api/2.1/jobs/run-now
notebooks/
  load_bronze.ipynb          # S3 → Delta Bronze
  silver_databricks.ipynb    # transformações Silver (PySpark)
dbt/models/
  staging/                   # limpeza e parse (Silver)
  marts/                     # modelo estrela (Gold)
.github/workflows/
  pipeline.yml               # trigger manual e schedule
```

## Dados e idempotência

Os JSONs (Bronze) e as tabelas Delta vivem no S3 (`s3://judicial-analytics-storage/`) e não são versionados. O watermark (`state/watermark.json`) registra a última data processada por tribunal, então reexecuções continuam de onde pararam. A prioridade da data de início é: watermark → input manual (`DATA_INICIO`) → padrão `2024-01-01`.
