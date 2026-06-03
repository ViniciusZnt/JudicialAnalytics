import json
import logging
import os
from datetime import date, timedelta

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from ingestion.datajud_client import DatajudClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET            = "judicial-analytics-storage"
TRIBUNAIS         = ["TJRS", "TJSC", "TJPR", "TJSP"]
WATERMARK_KEY     = "state/watermark.json"
DATA_INICIO_PADRAO = "2024-01-01"        # usado só na primeira execução

# Aqui é utilizado um watermark para que o github actions saiba qual execução ele parou


# ── Watermark ────────────────────────────────────────────────────────────────

def ler_watermark(s3) -> dict:
    """Retorna o último data_fim processado por tribunal."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=WATERMARK_KEY)
        return json.loads(obj["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return {}
        raise


def salvar_watermark(s3, watermark: dict) -> None:
    s3.put_object(
        Bucket=BUCKET,
        Key=WATERMARK_KEY,
        Body=json.dumps(watermark, indent=2),
        ContentType="application/json",
    )
    logger.info("Watermark atualizado: %s", watermark)


# ── Ingestão ─────────────────────────────────────────────────────────────────

def ingerir_tribunal(client: DatajudClient, s3, tribunal: str,
                     data_inicio: str, data_fim: str) -> bool:
    logger.info("%s: buscando %s → %s", tribunal, data_inicio, data_fim)
    dados = []

    for hits in client.paginate(tribunal, data_inicio, data_fim):
        dados.extend(hits)

    if not dados:
        logger.warning("%s: nenhum registro encontrado", tribunal)
        return False

    key = f"bronze/raw_files/{tribunal}/{data_inicio}_{data_fim}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(dados, ensure_ascii=False),
        ContentType="application/json",
    )
    logger.info("%s: %d registros → s3://%s/%s", tribunal, len(dados), BUCKET, key)
    return True


def main() -> None:
    client    = DatajudClient(api_key=os.environ["DATAJUD_API_KEY"])
    s3        = boto3.client("s3")
    watermark = ler_watermark(s3)

    # Override manual via env (workflow_dispatch) — senão usa watermark
    data_fim_global = os.getenv("DATA_FIM") or str(date.today())

    for tribunal in TRIBUNAIS:
        # DATA_INICIO: override manual > watermark > padrão inicial
        data_inicio = (
            os.getenv("DATA_INICIO")
            or watermark.get(tribunal)
            or DATA_INICIO_PADRAO
        )
        data_fim = data_fim_global

        if data_inicio >= data_fim:
            logger.info("%s: já atualizado até %s, pulando", tribunal, data_inicio)
            continue

        sucesso = ingerir_tribunal(client, s3, tribunal, data_inicio, data_fim)

        if sucesso:
            watermark[tribunal] = data_fim  # avança o ponteiro

    salvar_watermark(s3, watermark)


if __name__ == "__main__":
    main()