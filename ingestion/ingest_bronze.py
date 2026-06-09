import json
import logging
import os
import time
from datetime import date, datetime
import calendar

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from ingestion.datajud_client import DatajudClient, TransientApiError

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET             = "judicial-analytics-storage"
TRIBUNAIS          = ["TJRS", "TJSC", "TJPR", "TJSP"]
WATERMARK_KEY      = "state/watermark.json"
DATA_INICIO_PADRAO = "2024-01-01"
MAX_TENTATIVAS     = 3
ESPERA_BASE        = 10  # segundos entre tentativas


# ── Watermark ────────────────────────────────────────────────────────────────

def ler_watermark(s3) -> dict:
    """Retorna o último data_fim processado por tribunal."""
    logger.info("[WATERMARK] Lendo watermark do S3: s3://%s/%s", BUCKET, WATERMARK_KEY)
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=WATERMARK_KEY)
        watermark = json.loads(obj["Body"].read())
        logger.info("[WATERMARK] Watermark encontrado: %s", watermark)
        return watermark
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.info("[WATERMARK] Nenhum watermark encontrado — primeira execução, iniciando do zero")
            return {}
        raise


def salvar_watermark(s3, watermark: dict) -> None:
    logger.info("[WATERMARK] Salvando watermark atualizado: %s", watermark)
    s3.put_object(
        Bucket=BUCKET,
        Key=WATERMARK_KEY,
        Body=json.dumps(watermark, indent=2),
        ContentType="application/json",
    )
    logger.info("[WATERMARK] Watermark salvo com sucesso em s3://%s/%s", BUCKET, WATERMARK_KEY)


# ── Ingestão ─────────────────────────────────────────────────────────────────

def ingerir_tribunal(client: DatajudClient, s3, tribunal: str,
                     data_inicio: str, data_fim: str) -> bool:

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        logger.info("[%s] Tentativa %d/%d — buscando processos de %s até %s",
                    tribunal, tentativa, MAX_TENTATIVAS, data_inicio, data_fim)
        try:
            dados = []
            pagina = 1

            for hits in client.paginate(tribunal, data_inicio, data_fim):
                dados.extend(hits)
                logger.info("[%s] Página %d recebida — %d registros acumulados até agora",
                            tribunal, pagina, len(dados))
                pagina += 1

            if not dados:
                logger.warning("[%s] Nenhum registro encontrado no período %s → %s",
                               tribunal, data_inicio, data_fim)
                return False

            logger.info("[%s] Paginação concluída — total de %d registros coletados",
                        tribunal, len(dados))

            key = f"bronze/raw_files/{tribunal}/{data_inicio}_{data_fim}.json"
            logger.info("[%s] Gravando arquivo no S3: s3://%s/%s", tribunal, BUCKET, key)
            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=json.dumps(dados, ensure_ascii=False),
                ContentType="application/json",
            )
            logger.info("[%s] Arquivo gravado com sucesso — %d registros em s3://%s/%s",
                        tribunal, len(dados), BUCKET, key)
            return True

        except TransientApiError as e:
            if tentativa == MAX_TENTATIVAS:
                logger.error("[%s] Falhou após %d tentativas — abortando este tribunal. Erro: %s",
                             tribunal, MAX_TENTATIVAS, e)
                return False
            espera = ESPERA_BASE * tentativa
            logger.warning("[%s] Erro transiente na tentativa %d/%d — aguardando %ds antes de tentar novamente. Erro: %s",
                           tribunal, tentativa, MAX_TENTATIVAS, espera, e)
            time.sleep(espera)

    return False

# ── Validação Data ─────────────────────────────────────────────────────────────────
def data_valida(data_str: str) -> bool:
    try:
        datetime.strptime(data_str, "%Y-%m-%d")
        datetime.isocalendar()
        return True
    except ValueError:
        return False

def corrigir_data(data_str: str) -> str:
    """
    Recebe uma string no formato 'YYYY/MM/DD' e retorna a data corrigida.
    Se o dia for maior que o último dia do mês, ajusta para o último dia válido.
    Se o dia for menor que 1, ajusta para 1.
    Se o mês estiver fora de 1-12, ajusta para o limite mais próximo.
    """
    try:
        # Tenta interpretar diretamente a data
        ano, mes, dia = map(int, data_str.split('/'))
    except (ValueError, AttributeError):
        raise ValueError("Formato inválido. Use 'YYYY/MM/DD'")

    # Ajusta mês para o intervalo [1, 12]
    mes = max(1, min(mes, 12))

    # Obtém o último dia do mês
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    # Ajusta o dia
    if dia < 1:
        dia = 1
    elif dia > ultimo_dia:
        dia = ultimo_dia

    return f"{ano:04d}/{mes:02d}/{dia:02d}"



# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("[INICIO] Iniciando pipeline de ingestão DataJud")
    logger.info("[INICIO] Tribunais configurados: %s", TRIBUNAIS)

    client    = DatajudClient(api_key=os.environ["DATAJUD_API_KEY"], timeout=60)
    s3        = boto3.client("s3")
    watermark = ler_watermark(s3)

    data_fim_global = os.getenv("DATA_FIM") or str(date.today())
    logger.info("[CONFIG] Data fim global: %s", data_fim_global)
    
    if data_valida(data_fim_global):
        logger.info("[CONFIG] Data fim global: %s", data_fim_global)
        data_fim = data_fim_global
    else:
        data_fim = corrigir_data(data_fim_global)
        logger.error("[CONFIG] DATA_FIM inválida: '%s' — Corrijido para '%s'", data_fim_global, data_fim)
    

    origem_inicio = "variável de ambiente (override manual)" if os.getenv("DATA_INICIO") else "watermark ou padrão"
    logger.info("[CONFIG] Origem do data_inicio: %s", origem_inicio)

    resultados = {}

    for tribunal in TRIBUNAIS:
        logger.info("=" * 60)
        logger.info("[%s] Iniciando processamento", tribunal)

        data_inicio = (
            watermark.get(tribunal)
            or os.getenv("DATA_INICIO")
            or DATA_INICIO_PADRAO
        )

        if watermark.get(tribunal):
            logger.info("[%s] Watermark encontrado — continuando de %s", tribunal, watermark.get(tribunal))
        elif os.getenv("DATA_INICIO"):
            logger.info("[%s] Sem watermark — usando data_inicio do input manual: %s", tribunal, os.getenv("DATA_INICIO"))
        else:
            logger.info("[%s] Sem watermark — usando data padrão de início: %s", tribunal, DATA_INICIO_PADRAO)

        if data_inicio >= data_fim:
            logger.info("[%s] Já atualizado até %s — nada a buscar, pulando", tribunal, data_inicio)
            resultados[tribunal] = "pulado"
            continue

        sucesso = ingerir_tribunal(client, s3, tribunal, data_inicio, data_fim)

        if sucesso:
            watermark[tribunal] = data_fim
            resultados[tribunal] = "sucesso"
            logger.info("[%s] Processamento concluído — watermark avançado para %s", tribunal, data_fim)
        else:
            resultados[tribunal] = "falhou"
            logger.warning("[%s] Processamento falhou — watermark NÃO foi avançado", tribunal)

    logger.info("=" * 60)
    logger.info("[FIM] Resumo da execução:")
    for tribunal, status in resultados.items():
        logger.info("  %s → %s", tribunal, status)

    salvar_watermark(s3, watermark)
    logger.info("[FIM] Pipeline de ingestão finalizado")


if __name__ == "__main__":
    main()