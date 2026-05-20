import json
import logging
from datetime import datetime

import psycopg

logger = logging.getLogger(__name__)

BUFFER_SIZE = 100

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bronze_processos (
    id                          TEXT        PRIMARY KEY,
    numero_processo             TEXT        UNIQUE NOT NULL,
    tribunal                    TEXT        NOT NULL,
    data_ajuizamento            DATE,
    grau                        TEXT,
    nivel_sigilo                INTEGER,
    classe_codigo               INTEGER,
    classe_nome                 TEXT,
    orgao_julgador_codigo       INTEGER,
    orgao_julgador_nome         TEXT,
    orgao_julgador_municipio_ibge INTEGER,
    assuntos                    JSONB,
    movimentos                  JSONB,
    raw_data                    JSONB       NOT NULL,
    ingested_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_UPSERT = """
INSERT INTO bronze_processos (
    id, numero_processo, tribunal, data_ajuizamento, grau,
    nivel_sigilo, classe_codigo, classe_nome,
    orgao_julgador_codigo, orgao_julgador_nome, orgao_julgador_municipio_ibge,
    assuntos, movimentos, raw_data
) VALUES (
    %(id)s, %(numero_processo)s, %(tribunal)s, %(data_ajuizamento)s, %(grau)s,
    %(nivel_sigilo)s, %(classe_codigo)s, %(classe_nome)s,
    %(orgao_julgador_codigo)s, %(orgao_julgador_nome)s, %(orgao_julgador_municipio_ibge)s,
    %(assuntos)s, %(movimentos)s, %(raw_data)s
)
ON CONFLICT (id) DO NOTHING;
"""


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    logger.debug("Data não reconhecida, ignorando: %r", value)
    return None


class PostgresStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn = None
        self._buffer: list[dict] = []

    def connect(self) -> None:
        self._conn = psycopg.connect(self.database_url)
        with self._conn.cursor() as cur:
            cur.execute(_CREATE_TABLE)
        self._conn.commit()
        logger.info("PostgreSQL conectado — tabela bronze_processos pronta.")

    def close(self) -> None:
        if self._buffer:
            self._flush()
        if self._conn:
            self._conn.close()

    def append_hit(self, hit: dict) -> None:
        source = hit["_source"]
        classe = source.get("classe") or {}
        orgao = source.get("orgaoJulgador") or {}

        row = {
            "id":                             hit["_id"],
            "numero_processo":                source.get("numeroProcesso", ""),
            "tribunal":                       source.get("tribunal", ""),
            "data_ajuizamento":               _parse_date(source.get("dataAjuizamento", "")),
            "grau":                           source.get("grau"),
            "nivel_sigilo":                   source.get("nivelSigilo"),
            "classe_codigo":                  classe.get("codigo"),
            "classe_nome":                    classe.get("nome"),
            "orgao_julgador_codigo":          orgao.get("codigo"),
            "orgao_julgador_nome":            orgao.get("nome"),
            "orgao_julgador_municipio_ibge":  orgao.get("codigoMunicipioIBGE"),
            "assuntos":                       json.dumps(source.get("assuntos") or [], ensure_ascii=False),
            "movimentos":                     json.dumps(source.get("movimentos") or [], ensure_ascii=False),
            "raw_data":                       json.dumps(source, ensure_ascii=False),
        }

        self._buffer.append(row)
        if len(self._buffer) >= BUFFER_SIZE:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        try:
            with self._conn.cursor() as cur:
                cur.executemany(_UPSERT, self._buffer)
            self._conn.commit()
            logger.info("Flush: %d processos persistidos.", len(self._buffer))
        except Exception as exc:
            self._conn.rollback()
            logger.error("Erro no flush: %s", exc)
        finally:
            self._buffer.clear()
