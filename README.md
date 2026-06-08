# Judicial Analytics Platform

Plataforma analítica operacional do Judiciário brasileiro construída sobre dados públicos do CNJ.

Transforma eventos processuais brutos da API DataJud em métricas operacionais estruturadas — tempo médio de processamento, taxa de congestionamento, gargalos por fase — usando uma arquitetura medalhão em nuvem.

## Stack

| Camada | Tecnologia |
|---|---|
| Ingestão | Python + requests → **AWS S3** |
| Bronze | Arquivos JSON particionados no S3 (`bronze/raw_files/{tribunal}/`) |
| Silver | **Databricks** (notebooks PySpark) |
| Gold | **dbt-Databricks** (modelo estrela no Unity Catalog) |
| Orquestração | **GitHub Actions** (trigger manual + agendamento) |
| Dashboard | Streamlit |

## Arquitetura

```
API DataJud
    │
    ▼
GitHub Actions (pipeline.yml)
    │
    ├─ ingestion/ingest_bronze.py ──► S3 (bronze/raw_files/{tribunal}/)
    │       watermark em state/watermark.json
    │
    └─ ingestion/trigger_databricks_job.py ──► Databricks Job
                                                    │
                                              notebooks/
                                              ├── load_bronze.ipynb   (S3 → Delta Bronze)
                                              └── silver_databricks.ipynb (Bronze → Silver)
                                                    │
                                              dbt (Unity Catalog: judicial.gold)
                                              ├── dim_tribunais
                                              ├── dim_classes
                                              ├── dim_assuntos
                                              ├── dim_orgaos
                                              ├── dim_calendario
                                              └── fato_movimentos (incremental)
```

## Pré-requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — gerenciador de pacotes
- Conta AWS com bucket S3 `judicial-analytics-storage`
- Workspace Databricks com Unity Catalog

## Setup

### 1. Clonar o repositório

```bash
git clone https://github.com/ViniciusZnt/JudicialAnalytics.git
cd JudicialAnalytics
```

### 2. Instalar dependências

```bash
uv sync
```

### 3. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```bash
cp .env.example .env
```

Preencha as credenciais:

```env
# API DataJud (gratuita — solicite em datajud-wiki.cnj.jus.br)
DATAJUD_API_KEY=sua_chave_aqui

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1

# Databricks
DATABRICKS_HOST=https://dbc-xxxx.cloud.databricks.com
DATABRICKS_TOKEN=...
DATABRICKS_JOB_ID=...
```

### 4. Configurar o dbt

Edite `dbt/profiles.yml` com o host e http_path do seu Databricks SQL Warehouse:

```bash
uv run dbt deps --project-dir dbt/
```

## Pipeline

### Execução via GitHub Actions (recomendado)

Vá em **Actions → Pipeline Judicial → Run workflow** e informe o intervalo de datas:

| Input | Descrição | Padrão |
|---|---|---|
| `inicio` | Data início (YYYY-MM-DD) | `2025-01-01` |
| `fim` | Data fim (YYYY-MM-DD) | `2025-12-31` |

O workflow executa em sequência:
1. Ingestão DataJud → S3 (`ingestion/ingest_bronze.py`)
2. Trigger do Databricks Job (Bronze → Silver)
3. O job Databricks roda os notebooks e pode encadear o `dbt run`

### Execução local

**Só ingestão:**
```bash
uv run python -m ingestion.ingest_bronze
```

**Disparar job Databricks:**
```bash
uv run python -m ingestion.trigger_databricks_job
```

**Só transformações dbt (requer Databricks acessível):**
```bash
uv run dbt run --project-dir dbt/
uv run dbt test --project-dir dbt/
```

**Dashboard:**
```bash
uv run streamlit run dashboard/app.py
```

## Estrutura do projeto

```
JudicialAnalytics/
│
├── ingestion/
│   ├── datajud_client.py          # cliente HTTP da API DataJud (paginação search_after)
│   ├── ingest_bronze.py           # ingestão com watermark → S3
│   ├── trigger_databricks_job.py  # dispara job Databricks via REST API
│   └── test/
│       └── fetch_datajud.py       # testes de integração da ingestão
│
├── notebooks/
│   ├── load_bronze.ipynb          # S3 → Delta Bronze no Databricks
│   └── silver_databricks.ipynb    # Bronze → Silver (limpeza PySpark)
│
├── dbt/
│   ├── models/
│   │   ├── sources.yml            # fonte: camada Silver do Databricks
│   │   └── marts/                 # camada Gold — modelo estrela
│   │       ├── dim_tribunais.sql
│   │       ├── dim_classes.sql
│   │       ├── dim_assuntos.sql
│   │       ├── dim_orgaos.sql
│   │       ├── dim_calendario.sql
│   │       ├── fato_movimentos.sql  (incremental)
│   │       └── schema.yml           # testes dbt
│   ├── profiles.yml               # conexão Databricks SQL Warehouse
│   └── dbt_project.yml
│
├── dashboard/
│   └── app.py                     # Streamlit
│
├── .github/
│   └── workflows/
│       └── pipeline.yml           # GitHub Actions — trigger manual
│
└── pyproject.toml
```

## Modelo de dados (Gold)

O dbt materializa um modelo estrela no Unity Catalog `judicial.gold`:

| Tabela | Tipo | Descrição |
|---|---|---|
| `dim_tribunais` | dimensão | Uma linha por tribunal (TJRS, TJSC, TJPR, TJSP) |
| `dim_classes` | dimensão | Classes processuais CNJ |
| `dim_assuntos` | dimensão | Assuntos processuais CNJ |
| `dim_orgaos` | dimensão | Órgãos julgadores (varas, câmaras) |
| `dim_calendario` | dimensão | Datas de 2020 até hoje |
| `fato_movimentos` | fato incremental | Um evento por linha — `dias_desde_ajuizamento`, FKs para todas as dimensões |

## Watermark e idempotência

A ingestão mantém um arquivo `state/watermark.json` no S3 com o último `data_fim` processado por tribunal. Isso garante que reexecuções não reprocessem dados já ingeridos e que o pipeline possa ser retomado após falha.

Prioridade do `data_inicio` por tribunal:
1. Watermark no S3 (execuções anteriores)
2. Variável de ambiente `DATA_INICIO` (override manual)
3. Padrão hardcoded `2024-01-01`

## Escopo atual

- **Tribunais:** TJRS, TJSC, TJPR, TJSP
- **Período:** 2024 em diante (configurável)
- **Grau:** Primeiro grau (G1)
- **Métricas disponíveis na Gold:** TMP (`dias_desde_ajuizamento`), volume por tribunal/classe/órgão/período

## Dados

Os arquivos JSON da camada bronze ficam no S3 (`s3://judicial-analytics-storage/bronze/`) e não são versionados. Para regenerar, execute a etapa de ingestão com suas credenciais.
