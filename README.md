# Judicial Analytics Platform

Plataforma analítica operacional do Judiciário brasileiro construída sobre dados públicos do CNJ.

Transforma eventos processuais brutos da API DataJud em métricas operacionais estruturadas — tempo médio de processamento, taxa de congestionamento, gargalos por fase — cruzadas com os indicadores oficiais do Justiça em Números.

## Stack

| Camada | Tecnologia |
|---|---|
| Ingestão | Python + requests |
| Bronze | Arquivos JSON locais (`data/bronze/`) |
| Transformação | dbt-duckdb |
| Banco analítico | DuckDB |
| Dashboard | Streamlit |

## Pré-requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — gerenciador de pacotes

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

Edite `.env` e preencha sua chave da API DataJud:

```env
DATAJUD_API_KEY=sua_chave_aqui
```

A chave é gratuita — solicite em [datajud-wiki.cnj.jus.br](https://datajud-wiki.cnj.jus.br/).

### 4. Configurar o dbt

```bash
uv run dbt deps --project-dir dbt/
```

Isso instala o pacote `dbt-utils` declarado em `dbt/packages.yml`.

## Executar o pipeline completo

```bash
uv run python run_pipeline.py
```

O pipeline executa em sequência:

1. Ingestão da API DataJud → `data/bronze/`
2. Ingestão do Justiça em Números → `data/bronze/`
3. `dbt run` — staging + marts no DuckDB
4. `dbt test` — validação de qualidade

## Executar etapas individualmente

**Só ingestão:**
```bash
uv run python ingestion/fetch_datajud.py --tribunais TJSC,TJPR --inicio 2023-01-01
```

**Só transformações dbt:**
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
judicial-analytics/
│
├── ingestion/
│   ├── datajud_client.py     # cliente HTTP da API DataJud
│   ├── core_ingestion.py     # paginação com search_after
│   └── fetch_datajud.py      # script principal de ingestão
│
├── data/
│   └── bronze/               # JSONs brutos por tribunal/data (gitignored)
│
├── dbt/
│   ├── models/
│   │   ├── staging/          # limpeza, parse, campos calculados
│   │   └── marts/            # dimensões, fatos, agregações
│   ├── tests/                # testes customizados
│   ├── packages.yml          # dbt-utils
│   └── dbt_project.yml
│
├── dashboard/
│   └── app.py                # Streamlit
│
├── run_pipeline.py           # executa tudo em sequência
├── pyproject.toml
└── judicial_analytics_platform.md   # especificação técnica completa
```

## Escopo do MVP

- **Tribunais:** TJSC e TJPR
- **Período:** 2023–2024
- **Grau:** Primeiro grau (G1)
- **Métricas:** TMP, taxa de congestionamento, gargalo por fase, benchmarking DataJud × Justiça em Números

## DuckDB — banco analítico local

O projeto usa DuckDB como banco analítico. Ao contrário de um banco servidor, DuckDB é um único arquivo (`judicial.duckdb`) gerado pelo `dbt run` e consultado diretamente — sem processo separado rodando.

O dbt organiza as tabelas em dois schemas dentro do arquivo:

| Schema | Conteúdo | Equivalente na arquitetura medalhão |
|---|---|---|
| `staging` | `stg_datajud__*`, `stg_jen__*` | Silver — dados limpos e normalizados |
| `marts` | `dim_*`, `fato_*`, `agg_*` | Gold — modelo estrela pronto para análise |

A camada Bronze não fica no DuckDB — são os arquivos JSON em `data/bronze/`, lidos diretamente pelo dbt via `read_json()` do DuckDB.

**Consultar o banco pelo terminal:**

```bash
uv run duckdb judicial.duckdb
```

Exemplos de consulta:

```sql
-- listar todas as tabelas
SHOW ALL TABLES;

-- ver os processos na staging
SELECT * FROM staging.stg_datajud__processos LIMIT 10;

-- consulta analítica: TMP médio por tribunal
SELECT
    t.nome_tribunal,
    AVG(f.dias_desde_ajuizamento) AS tmp_medio_dias
FROM marts.fato_movimentos f
JOIN marts.dim_tribunais t ON f.sk_tribunal = t.sk_tribunal
WHERE f.is_ultimo_movimento = true
GROUP BY t.nome_tribunal
ORDER BY tmp_medio_dias DESC;
```

## Dados

Os arquivos JSON da camada bronze não são versionados (`.gitignore`). Para regenerar, execute a etapa de ingestão com suas credenciais.

O banco DuckDB (`judicial.duckdb`) também não é versionado — é gerado localmente pelo `dbt run`.
