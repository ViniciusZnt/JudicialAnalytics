# Judicial Operational Analytics Platform
### Documento de Viabilidade e Especificação Técnica — v1.0

---

## 1. Síntese Executiva

Este projeto constrói uma **plataforma analítica operacional do Judiciário brasileiro** a partir de dados públicos do CNJ. A proposta não é criar um dashboard avulso — é construir uma infraestrutura de dados capaz de responder perguntas operacionais que hoje exigem trabalho manual extenso ou simplesmente não têm resposta acessível.

**Proposta de valor central:**
> Transformar eventos processuais brutos do DataJud em inteligência operacional estruturada, comparável e histórica — cruzada com os indicadores oficiais do Justiça em Números.

**Stack deliberadamente modesta:** o objetivo é dominar os fundamentos de engenharia de dados — ingestão, modelagem, qualidade, orquestração — sem a complexidade operacional de um cluster distribuído. A mesma arquitetura medalhão e o mesmo modelo estrela de uma plataforma enterprise, rodando local com zero infraestrutura.

---

## 2. Fontes de Dados — Especificação Real

### 2.1 DataJud

| Atributo | Detalhe |
|---|---|
| Tipo | API REST (Elasticsearch) |
| Base URL | `https://datajud-wiki.cnj.jus.br/` |
| Autenticação | API Key via header `Authorization: ApiKey <chave>` |
| Disponibilidade | Acesso público (chave gratuita) |
| Volume estimado | ~120M de processos ativos + histórico |
| Granularidade | Evento por movimentação processual |
| Formato de resposta | JSON (estrutura Elasticsearch hits) |
| Rate limit | Sim — necessário controle de requisições |
| Cobertura | Todos os tribunais brasileiros (Justiça Federal, Estadual, Trabalho, Militar, Eleitoral) |

**Endpoint principal:**
```
POST https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search
```

**Exemplo de payload:**
```json
{
  "query": {
    "match": { "tribunal": "TJSC" }
  },
  "sort": [{ "dataAjuizamento": { "order": "desc" } }],
  "size": 10000
}
```

**Estrutura de retorno (campos-chave):**

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string | Identificador único do processo |
| `numeroProcesso` | string | Número CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO) |
| `tribunal` | string | Sigla do tribunal |
| `dataAjuizamento` | datetime | Data de distribuição |
| `classeProcessual.codigo` | int | Código da classe (tabela CNJ) |
| `assuntos[].codigo` | int | Código(s) do(s) assunto(s) |
| `movimentos[]` | array | Lista de movimentações com código e data |
| `orgaoJulgador.codigo` | string | Código do órgão julgador |
| `grau` | string | Instância (G1, G2, JE, SUP) |

**Desafios reais desta fonte:**
- Paginação via `search_after` (não `from/size` — limitação do Elasticsearch público)
- Dados retroativos podem ter inconsistências de codificação entre tribunais
- Volume por tribunal varia enormemente (TJSP ≫ TJ de estados menores)

---

### 2.2 Tabelas Unificadas CNJ

| Atributo | Detalhe |
|---|---|
| Tipo | API REST + arquivos estáticos |
| Base URL | `https://www.cnj.jus.br/sgt/consulta_publica_classes.php` |
| Formato | JSON / CSV |
| Conteúdo | Classes, assuntos, movimentos, complementos |
| Frequência de atualização | Baixa (meses) — pode ser cached |

**Tabelas essenciais para o projeto:**

| Tabela | Uso analítico |
|---|---|
| `classes_processuais` | Identificar tipo de ação (ex: "Ação Civil Pública") |
| `assuntos` | Área do direito (ex: "Direito do Consumidor") |
| `movimentos` | Fase processual (ex: "Conclusão para Sentença") |
| `orgaos_julgadores` | Vara / câmara responsável |

**Estratégia de uso:** carga inicial completa + refresh semanal automatizado. Armazenar como tabelas de dimensão no DuckDB.

---

### 2.3 Justiça em Números

| Atributo | Detalhe |
|---|---|
| Tipo | Arquivos Excel/CSV para download |
| Fonte | `https://www.cnj.jus.br/pesquisas-judiciarias/justica-em-numeros/` |
| Granularidade | Anual, por tribunal |
| Séries disponíveis | 2009–2024 (aproximadamente) |

**Indicadores estratégicos disponíveis:**

| Indicador | Definição |
|---|---|
| `taxa_congestionamento` | `(pendentes_final / (pendentes_inicial + ingressos)) × 100` |
| `ipc` | Índice de Produtividade por Magistrado |
| `casos_novos` | Volume de processos ingressados no ano |
| `casos_baixados` | Processos encerrados (por qualquer forma) |
| `acervo` | Total de processos pendentes ao final do período |

**Valor analítico cruzado:** estes indicadores permitem validar e contextualizar as métricas calculadas a partir do DataJud, criando uma camada de benchmarking comparável ao padrão do CNJ.

---

## 3. Arquitetura Técnica

### 3.1 Visão por Camadas (Medalhão)

```
┌─────────────────────────────────────────────────────────────┐
│  FONTES EXTERNAS                                            │
│  DataJud API │ CNJ Tabelas API │ Justiça em Números (xlsx)  │
└────────────────────────┬────────────────────────────────────┘
                         │ ingestion/ (Python + requests)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  BRONZE — data/bronze/  (arquivos JSON por tribunal)        │
│  • Dados brutos, sem transformação                          │
│  • Um arquivo por execução — preserva histórico             │
│  • Nomenclatura: {tribunal}_{data_ref}.json                 │
└────────────────────────┬────────────────────────────────────┘
                         │ dbt (source → staging)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  SILVER — DuckDB  (tabelas staging_*)                       │
│  • Deduplicação de processos e movimentos                   │
│  • Parsing do número CNJ                                    │
│  • Enriquecimento com tabelas CNJ                           │
│  • Normalização de datas e tipos                            │
│  • Campos calculados: dias_desde_ajuizamento, fase          │
└────────────────────────┬────────────────────────────────────┘
                         │ dbt (staging → marts)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  GOLD — DuckDB  (tabelas marts/)                            │
│  fato_movimentos         dim_classes                        │
│  fato_indicadores_jen    dim_assuntos                       │
│  agg_tempo_tramitacao    dim_tribunais                      │
│  agg_congestionamento    dim_orgaos                         │
│                          dim_calendario                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  CONSUMO                                                    │
│  Streamlit dashboard │ DuckDB CLI │ Jupyter notebooks        │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.2 Modelo de Dados Gold (Esquema Estrela)

**Princípio:** surrogate keys (`sk_*`) são chaves primárias das dimensões geradas via `dbt_utils.generate_surrogate_key`. As tabelas fato referenciam as dimensões pelas FKs — sem atributos descritivos.

---

#### Dimensões

**`dim_classes`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_classe` | varchar | **PK — surrogate key gerada pelo dbt** |
| `codigo_classe` | int | Chave natural (código CNJ) |
| `nome_classe` | varchar | Ex: "Ação Civil Pública" |
| `grupo_classe` | varchar | Agrupamento analítico |
| `competencia` | varchar | Civil, Penal, Trabalhista etc. |

**`dim_assuntos`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_assunto` | varchar | **PK — surrogate key** |
| `codigo_assunto` | int | Chave natural |
| `nome_assunto` | varchar | Ex: "Direito do Consumidor" |
| `assunto_pai_codigo` | int | Hierarquia CNJ (árvore) |
| `nivel_hierarquia` | int | Profundidade na árvore de assuntos |

**`dim_tribunais`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_tribunal` | varchar | **PK — surrogate key** |
| `sigla_tribunal` | varchar | Chave natural (ex: "TJSC") |
| `nome_tribunal` | varchar | Nome completo |
| `segmento_justica` | varchar | Estadual, Federal, Trabalhista, Eleitoral, Militar |
| `uf` | varchar | Unidade federativa |
| `regiao` | varchar | Norte, Nordeste, Centro-Oeste, Sudeste, Sul |

**`dim_orgaos`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_orgao` | varchar | **PK — surrogate key** |
| `codigo_orgao` | varchar | Chave natural |
| `nome_orgao` | varchar | Ex: "1ª Vara Cível de SP" |
| `sk_tribunal` | varchar | FK → dim_tribunais |
| `tipo_orgao` | varchar | Vara, Câmara, Turma, Pleno |
| `municipio` | varchar | Localização |

**`dim_calendario`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_data` | int | **PK — formato YYYYMMDD** |
| `data` | date | Chave natural |
| `ano` | int | Ano |
| `mes` | int | Mês numérico |
| `trimestre` | int | 1–4 |
| `dia_semana` | varchar | Segunda … Domingo |
| `is_fim_de_semana` | boolean | Sábado ou domingo |
| `is_feriado_nacional` | boolean | Feriados que suspendem prazos |

---

#### Tabela Fato Principal: `fato_movimentos`

Identificada pela combinação `(numero_processo, codigo_movimento, data_movimento)`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `numero_processo` | varchar | Chave natural do processo (número CNJ) |
| `sk_classe` | varchar | FK → dim_classes |
| `sk_assunto_principal` | varchar | FK → dim_assuntos |
| `sk_tribunal` | varchar | FK → dim_tribunais |
| `sk_orgao` | varchar | FK → dim_orgaos |
| `sk_data_movimento` | int | FK → dim_calendario |
| `sk_data_ajuizamento` | int | FK → dim_calendario |
| `codigo_movimento` | int | Código CNJ do evento |
| `nome_movimento` | varchar | Descrição enriquecida |
| `tipo_fase` | varchar | Fase normalizada (ex: "sentença") |
| `grau` | varchar | G1, G2, JE, SUP |
| `dias_desde_ajuizamento` | int | datediff acumulado |
| `dias_desde_ultimo_movimento` | int | lag entre movimentos |
| `is_ultimo_movimento` | boolean | Flag de estado atual do processo |

#### Tabela Fato Secundária: `fato_indicadores_jen`

| Coluna | Tipo | Descrição |
|---|---|---|
| `sk_tribunal` | varchar | FK → dim_tribunais |
| `ano_referencia` | int | Ano do relatório |
| `taxa_congestionamento` | double | Indicador oficial CNJ |
| `casos_novos` | bigint | Volume processual |
| `casos_baixados` | bigint | Processos encerrados |
| `acervo_final` | bigint | Pendentes ao final |
| `ipc_1grau` | double | Produtividade magistrado 1º grau |

---

### 3.3 Transformações Críticas (Python + dbt)

**1. Ingestão paginada com search_after**
```python
import requests
import json
import time
from pathlib import Path

def fetch_tribunal(tribunal: str, data_inicio: str, api_key: str) -> list[dict]:
    url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal.lower()}/_search"
    headers = {"Authorization": f"ApiKey {api_key}", "Content-Type": "application/json"}
    resultados = []
    search_after = None

    while True:
        payload = {
            "size": 10000,
            "sort": [{"dataAjuizamento": "desc"}, {"_id": "asc"}],
            "query": {"range": {"dataAjuizamento": {"gte": data_inicio}}},
        }
        if search_after:
            payload["search_after"] = search_after

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        hits = resp.json()["hits"]["hits"]

        if not hits:
            break

        resultados.extend(hits)
        search_after = hits[-1]["sort"]
        time.sleep(0.5)  # respeitar rate limit

    return resultados

def salvar_bronze(tribunal: str, dados: list[dict], data_ref: str):
    path = Path(f"data/bronze/{tribunal}_{data_ref}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
```

**2. Leitura do Bronze no dbt com DuckDB**
```sql
-- models/staging/stg_datajud__movimentos.sql
-- Lê os JSON do Bronze diretamente via read_json do DuckDB

with source as (
    select * from read_json(
        'data/bronze/TJSC_*.json',
        format = 'array',
        columns = {
            '_id': 'varchar',
            '_source': 'json'
        }
    )
),

parsed as (
    select
        _id,
        json_extract_string(_source, '$.numeroProcesso')  as numero_processo,
        json_extract_string(_source, '$.tribunal')        as tribunal,
        cast(json_extract_string(_source, '$.dataAjuizamento') as date) as data_ajuizamento,
        json_extract(_source, '$.classeProcessual.codigo')::int          as codigo_classe,
        json_extract_string(_source, '$.grau')            as grau,
        json_extract(_source, '$.movimentos')             as movimentos_raw
    from source
)

select * from parsed
```

**3. Explosão de movimentos (unnest)**
```sql
-- models/staging/stg_datajud__movimentos_explodido.sql

with base as (
    select * from {{ ref('stg_datajud__processos') }}
),

explodido as (
    select
        numero_processo,
        tribunal,
        data_ajuizamento,
        grau,
        unnest(
            from_json(movimentos_raw, '["json"]')
        ) as movimento
    from base
)

select
    numero_processo,
    tribunal,
    data_ajuizamento,
    grau,
    json_extract(movimento, '$.codigo')::int          as codigo_movimento,
    cast(json_extract_string(movimento, '$.dataHora') as date) as data_movimento
from explodido
```

**4. Campos temporais e fases (window functions em SQL)**
```sql
-- models/staging/stg_datajud__movimentos_enriquecido.sql

with movimentos as (
    select * from {{ ref('stg_datajud__movimentos_explodido') }}
),

com_temporais as (
    select
        *,
        datediff('day', data_ajuizamento, data_movimento)   as dias_desde_ajuizamento,
        datediff('day',
            lag(data_movimento) over (
                partition by numero_processo order by data_movimento
            ),
            data_movimento
        )                                                    as dias_desde_ultimo_movimento,
        row_number() over (
            partition by numero_processo order by data_movimento desc
        ) = 1                                               as is_ultimo_movimento
    from movimentos
)

select * from com_temporais
```

---

## 4. Métricas Analíticas — Especificação

### 4.1 Métricas Operacionais (DataJud)

| Métrica | Definição técnica | Aplicação |
|---|---|---|
| **TMP** (Tempo Médio de Processamento) | `AVG(data_baixa - data_ajuizamento)` por tribunal/classe/grau | Benchmark de eficiência |
| **Taxa de movimentação** | `COUNT(movimentos) / COUNT(processos)` por período | Atividade do órgão |
| **Índice de gargalo por fase** | Fase com maior `AVG(dias_desde_ultimo_movimento)` | Onde processos ficam parados |
| **Taxa de recorribilidade** | `COUNT(com_recurso) / COUNT(com_sentença)` | Qualidade decisória |
| **Distribuição por assunto** | Volume e TMP segmentado por assunto CNJ | Especialização de varas |
| **Anomalias de inatividade** | Processos sem movimentação há >180 dias | Detecção de backlog oculto |

### 4.2 Métricas de Benchmarking (DataJud × Justiça em Números)

| Comparação | Pergunta real |
|---|---|
| TMP calculado vs. IPC oficial | "A produtividade oficial do CNJ é consistente com o tempo real dos processos?" |
| Volume ingressado vs. casos novos JeN | "A cobertura do DataJud para este tribunal é completa?" |
| Taxa de congestionamento calculada vs. oficial | "Há divergência entre o que calculamos e o que o CNJ reporta?" |

---

## 5. Pipelines — Especificação de Workflows

A orquestração usa scripts Python com dependências explícitas. Sem servidor, sem scheduler externo — o pipeline roda com `python run_pipeline.py`.

### Pipeline completo
```
python ingestion/fetch_datajud.py --tribunais TJSC,TJPR --inicio 2023-01-01
    → data/bronze/{tribunal}_{data}.json

dbt run --select staging
    → DuckDB: staging_*

dbt run --select marts
    → DuckDB: dim_*, fato_*, agg_*

dbt test
    → validação de qualidade em todas as camadas

streamlit run dashboard/app.py
    → UI no browser
```

### Estrutura de execução
```python
# run_pipeline.py
from ingestion.fetch_datajud import fetch_all_tribunais
from ingestion.fetch_jen import fetch_jen
import subprocess

def run():
    fetch_all_tribunais(tribunais=["TJSC", "TJPR"], inicio="2023-01-01")
    fetch_jen()
    subprocess.run(["dbt", "run"], check=True)
    subprocess.run(["dbt", "test"], check=True)

if __name__ == "__main__":
    run()
```

---

## 6. Modelo de Qualidade de Dados

Cada camada tem contratos explícitos via `dbt test`:

| Teste | Camada | Descrição |
|---|---|---|
| `not_null(numero_processo)` | Staging | Todo processo tem número |
| `unique(numero_processo, codigo_movimento, data_movimento)` | Gold | Sem duplicatas na fato |
| `accepted_values(grau, ['G1','G2','JE','SUP'])` | Staging | Grau dentro do domínio |
| `relationships(sk_classe → dim_classes)` | Gold | Integridade referencial |
| `relationships(sk_tribunal → dim_tribunais)` | Gold | Integridade referencial |
| `not_null(dias_desde_ajuizamento)` | Gold | Campo calculado não nulo |
| `dbt_utils.expression_is_true(dias_desde_ajuizamento >= 0)` | Gold | Dias não negativos |

---

## 7. Escopo do MVP

### Recorte MVP

| Dimensão | Decisão |
|---|---|
| Tribunais | TJSC + TJPR (Sul do Brasil — volume gerenciável, boa cobertura DataJud) |
| Período histórico | Últimos 2 anos (2023–2024) |
| Classes processuais | Top 10 por volume (cobre ~70% dos processos) |
| Grau | Apenas G1 (primeiro grau) |
| Métricas | TMP, taxa de congestionamento calculada, gargalo por fase |

### Entregáveis do MVP

1. **Pipeline funcional** Bronze → Staging → Gold para os 2 tribunais
2. **dbt models** principais: `fato_movimentos`, `agg_tempo_tramitacao`, `agg_congestionamento`
3. **Dashboard Streamlit** com: ranking de congestionamento por tribunal/vara, TMP por classe processual, evolução mensal do acervo
4. **Comparação DataJud × JeN** para TJSC e TJPR no período

### O que fica fora do MVP (mas já arquitetado)

- Cobertura nacional
- Análise de segundo grau e instâncias superiores
- Detecção de anomalias automatizada
- Curva de sobrevivência processual

---

## 8. Stack Técnica Final

| Componente | Tecnologia | Justificativa |
|---|---|---|
| Ingestão | Python + requests | Controle total da paginação, rate limit, retry |
| Storage Bronze | Arquivos JSON locais | Zero infra, auditável, reprocessável |
| Banco analítico | DuckDB | Columnar, zero infra, lê JSON/Parquet nativamente, excelente suporte dbt |
| Transformação | dbt-duckdb | Modelagem declarativa, testes nativos, lineage, documentação automática |
| Orquestração | Script Python | Sem overhead de scheduler para MVP — complexidade cresce com a necessidade |
| Dashboard | Streamlit | Python-first, zero configuração, suficiente para portfólio |
| Ambiente | uv + pyproject.toml | Reproducibilidade, dependências versionadas |

---

## 9. Estrutura de Repositório

```
judicial-analytics/
│
├── ingestion/
│   ├── fetch_datajud.py      ← paginação, rate limit, salva bronze
│   └── fetch_jen.py          ← download e parse do xlsx JeN
│
├── data/
│   └── bronze/               ← JSON brutos por tribunal/data (gitignored)
│
├── dbt/
│   ├── models/
│   │   ├── staging/          ← limpeza, parse, campos calculados
│   │   └── marts/            ← dimensões, fatos, agregações
│   ├── tests/                ← testes customizados
│   └── dbt_project.yml
│
├── dashboard/
│   └── app.py                ← Streamlit
│
├── run_pipeline.py           ← executa tudo em sequência
├── pyproject.toml
└── judicial_analytics_platform.md
```

---

## 10. O Que Este Projeto Demonstra

Do ponto de vista de engenharia de dados, este projeto evidencia:

- **Engenharia de ingestão real** — API paginada, rate limit, schema validation
- **Modelagem analítica** — esquema estrela, fatos e dimensões bem definidos, surrogate keys
- **Qualidade de dados** — contratos explícitos via dbt test, não assumidos
- **Pensamento em camadas** — decisões deliberadas por camada (bronze/staging/gold)
- **Pensamento temporal** — histórico, reprocessamento, dados retroativos
- **SQL analítico avançado** — window functions, unnest, joins complexos
- **Domínio aplicado** — entendimento do processo judicial como objeto de análise

A combinação de **dados públicos reais + problema genuinamente complexo + stack usada em produção** é o que diferencia este projeto de exercícios acadêmicos.

---

## 11. Fluxo de Desenvolvimento

### Como funciona o ciclo

```
Você lê o brief do milestone
    → pesquisa o que não sabe
    → escreve o código
    → cola aqui no chat para revisão
    → ajusta e itera
    → só avança quando o atual estiver entendido
```

O objetivo não é entregar o projeto — é você sair de cada milestone conseguindo explicar o que escreveu.

---

### Milestones

---

#### M1 — Primeiro contato com a API DataJud

**O que você vai construir:** um script Python que faz uma requisição real para a API do DataJud, recupera processos do TJSC e exibe os dados no terminal de forma legível.

**Resultado esperado:** rodar `python ingestion/fetch_datajud.py` e ver no terminal uma lista com número do processo, data de ajuizamento e o nome do último movimento de pelo menos 10 processos reais do TJSC.

**O que você vai aprender:** como funciona uma requisição POST com autenticação via header, como navegar em uma resposta JSON aninhada, e por que a API do DataJud usa `search_after` em vez de paginação simples.

**Antes de codar, pesquise:**
- O que é uma requisição POST e como ela difere de GET
- Como passar headers de autenticação no `requests`
- O que é Elasticsearch e por que `search_after` existe
- Documentação do DataJud: `https://datajud-wiki.cnj.jus.br/`

**Detalhes técnicos:**
- Endpoint: `POST https://api-publica.datajud.cnj.jus.br/api_publica_tjsc/_search`
- Header: `Authorization: ApiKey SUA_CHAVE`
- A resposta vem em `response.json()["hits"]["hits"]`
- Cada processo tem um campo `_source` com os dados reais

**Critérios:**
- O script roda sem erro
- A saída no terminal é legível (não um dump bruto de JSON)
- Você sabe o que está dentro de `_source` e quais campos existem
- Você consegue explicar o que é `search_after` e por que ele existe

---

#### M2 — Paginação completa e carga Bronze

**O que você vai construir:** o script `ingestion/fetch_datajud.py` com paginação via `search_after`, rate limit, e salvamento dos JSON em `data/bronze/`.

**Resultado esperado:** rodar o script com `--tribunais TJSC,TJPR --inicio 2024-01-01` e encontrar os arquivos `data/bronze/TJSC_2024-01-01.json` e `data/bronze/TJPR_2024-01-01.json` com todos os processos do período. Rodar duas vezes sobrescreve sem duplicar.

**O que você vai aprender:** como implementar paginação com `search_after`, como controlar rate limit com `time.sleep`, e como usar `argparse` para CLI.

**Antes de codar, pesquise:**
- Como funciona `search_after` no Elasticsearch — o que é o campo `sort` na resposta
- Como usar `argparse` para aceitar argumentos de linha de comando
- Por que sobrescrever o arquivo é preferível a concatenar para manter idempotência

**Detalhes técnicos:**
- A paginação para quando `hits` retorna lista vazia
- Cada página: passe `"search_after": hits[-1]["sort"]` na próxima requisição
- Salve como JSON array: `json.dumps(resultados, ensure_ascii=False, indent=2)`
- Nomenclatura: `data/bronze/{tribunal}_{data_inicio}.json`

**Critérios:**
- O script aceita `--tribunais` e `--inicio` como argumentos
- Rodar duas vezes com os mesmos argumentos produz o mesmo arquivo
- Você sabe explicar por que o arquivo final é idempotente

---

#### M3 — Setup dbt + primeira model staging

**O que você vai construir:** o projeto dbt conectado ao DuckDB e a primeira model `stg_datajud__processos` que lê os JSON do Bronze e expõe os campos principais limpos.

**Resultado esperado:** rodar `dbt run --select stg_datajud__processos` e consultar a tabela no DuckDB com `numero_processo`, `tribunal`, `data_ajuizamento`, `grau`, `codigo_classe` tipados corretamente.

**O que você vai aprender:** como configurar dbt com DuckDB, o que é uma `source` no dbt, como usar `read_json` do DuckDB para ler arquivos externos, e o conceito de materialização.

**Antes de codar, pesquise:**
- Como instalar `dbt-duckdb` e inicializar um projeto dbt
- O que é `profiles.yml` e como configurar uma connection DuckDB
- O que é uma `source` no dbt e por que ela existe (diferente de um `ref`)
- Como `read_json` do DuckDB lê múltiplos arquivos com glob (`data/bronze/TJSC_*.json`)

**Detalhes técnicos:**
- `profiles.yml`: `type: duckdb`, `path: judicial.duckdb`
- Source aponta para `data/bronze/` — não é uma tabela, é um arquivo
- Use `read_json` com `format = 'array'` para ler o JSON array salvo na ingestão
- Extraia campos do `_source` com `json_extract_string(_source, '$.campo')`

**Critérios:**
- `dbt run` completa sem erros
- Você consegue `SELECT * FROM stg_datajud__processos LIMIT 10` no DuckDB CLI
- Os tipos estão corretos (data como `date`, não `varchar`)
- Você consegue explicar a diferença entre `source` e `ref` no dbt

---

#### M4 — Staging completa: movimentos explodidos e campos temporais

**O que você vai construir:** as models `stg_datajud__movimentos` (unnest do array de movimentos) e `stg_datajud__movimentos_enriquecido` (com campos temporais via window functions).

**Resultado esperado:** uma tabela onde cada linha é um movimento de um processo, com `dias_desde_ajuizamento`, `dias_desde_ultimo_movimento` e `is_ultimo_movimento` calculados corretamente.

**O que você vai aprender:** o que é `unnest` e por que ele é necessário quando um campo é um array JSON, como funcionam window functions em SQL (`LAG`, `ROW_NUMBER`), e como encadear models com `ref()`.

**Antes de codar, pesquise:**
- O que é `unnest` em SQL — quando você tem um array numa coluna e quer uma linha por elemento
- O que é uma window function — diferença entre `GROUP BY` e `PARTITION BY`
- As funções `LAG()`, `DATEDIFF()` e `ROW_NUMBER()` no DuckDB
- Como usar `{{ ref('modelo_anterior') }}` para encadear models no dbt

**Detalhes técnicos:**
- `unnest(from_json(movimentos_raw, '["json"]'))` expande o array
- Window: `PARTITION BY numero_processo ORDER BY data_movimento`
- `LAG(data_movimento)` retorna a data do movimento anterior — use com `DATEDIFF` para o intervalo
- `ROW_NUMBER() ... ORDER BY data_movimento DESC = 1` marca o último movimento

**Critérios:**
- Cada linha representa exatamente um movimento de um processo
- `dias_desde_ajuizamento` não tem valores negativos
- `is_ultimo_movimento` é `true` em exatamente uma linha por processo
- Você consegue explicar por que `GROUP BY` não resolveria o problema de `LAG`

---

#### M5 — Gold: dimensões

**O que você vai construir:** as cinco dimensões (`dim_tribunais`, `dim_classes`, `dim_assuntos`, `dim_orgaos`, `dim_calendario`) com surrogate keys geradas pelo dbt e testes de unicidade.

**Resultado esperado:** `dbt run --select marts.dims` cria as cinco tabelas no DuckDB com `sk_*` como PK e nenhuma duplicata — confirmado por `dbt test`.

**O que você vai aprender:** o que é surrogate key e por que usar `dbt_utils.generate_surrogate_key` em vez da chave natural, e como escrever testes de schema no dbt.

**Antes de codar, pesquise:**
- O que é surrogate key — diferença conceitual para chave natural
- Como instalar e usar `dbt_utils` — o package mais comum do ecossistema dbt
- Como declarar testes `unique` e `not_null` no `schema.yml`
- Como gerar a `dim_calendario` sem fonte externa (sequência de datas)

**Detalhes técnicos:**
- Surrogate key: `{{ dbt_utils.generate_surrogate_key(['codigo_classe']) }}`
- `dim_calendario`: gere com `SELECT UNNEST(GENERATE_SERIES(DATE '2020-01-01', CURRENT_DATE, INTERVAL 1 DAY)) AS data`
- Teste de unicidade no `schema.yml`: `- unique` e `- not_null` na coluna `sk_*`

**Critérios:**
- `dbt test --select marts.dims` passa sem falhas
- Você consegue explicar por que `sk_classe != codigo_classe`
- `dim_calendario` tem um registro por dia de 2020 até hoje

---

#### M6 — Gold: tabela fato

**O que você vai construir:** a `fato_movimentos` partindo da staging enriquecida, resolvendo todas as FKs com JOIN nas dimensões, sem nenhum atributo descritivo.

**Resultado esperado:** `dbt run --select fato_movimentos` cria a tabela com apenas FKs e métricas. Uma query juntando fato + dimensões retorna resultado com significado de negócio.

**O que você vai aprender:** a regra de ouro do star schema (fato só tem métricas e FKs), como fazer múltiplos JOINs em SQL, e como verificar integridade referencial com testes dbt.

**Detalhes técnicos:**
- Parta de `{{ ref('stg_datajud__movimentos_enriquecido') }}`
- Para cada dimensão: `LEFT JOIN {{ ref('dim_tribunais') }} USING (sigla_tribunal)` — selecione apenas `sk_tribunal`
- O model final não deve ter nenhuma coluna descritiva
- Teste de integridade: `relationships` no `schema.yml` para cada FK

**Critérios:**
- Nenhuma coluna descritiva na fato (ex: `nome_tribunal` não está aqui)
- `dbt test --select fato_movimentos` passa os testes de relacionamento
- Você consegue fazer uma query de negócio com JOIN fato + dims e obter resultado com significado

---

#### M7 — Agregações e dashboard

**O que você vai construir:** as models `agg_tempo_tramitacao` e `agg_congestionamento`, e um dashboard Streamlit que as consome.

**Resultado esperado:** `streamlit run dashboard/app.py` abre no browser com ranking de congestionamento por tribunal e TMP por classe processual.

**O que você vai aprender:** como materializar models dbt como tabelas para servir dashboards, como conectar Streamlit ao DuckDB, e como apresentar dados analíticos de forma legível.

**Detalhes técnicos:**
- Agregações: materialize como `table` no dbt para evitar recalcular no dashboard
- Streamlit + DuckDB: `import duckdb; conn = duckdb.connect('judicial.duckdb')`
- Use `conn.execute("SELECT ...").df()` para retornar pandas DataFrame
- Streamlit: `st.dataframe()`, `st.bar_chart()`, `st.line_chart()`

**Critérios:**
- O dashboard carrega sem erros
- Ranking de congestionamento mostra diferença real entre TJSC e TJPR
- Você consegue explicar por que as agregações são materializadas como `table` e não `view`

---

### Dinâmica de revisão

Quando colar o código aqui, a revisão vai seguir sempre o mesmo formato:

- **O que está bom** — para você saber o que já consolidou
- **O que precisa ajustar** — com explicação do porquê, não só o quê
- **Uma pergunta** — para verificar se o entendimento está lá, não só o código

Não avance de milestone sem passar pela revisão.

---

*Versão 1.0 — Stack redesenhada: Python + DuckDB + dbt + Streamlit. Mesma arquitetura, zero infraestrutura.*
