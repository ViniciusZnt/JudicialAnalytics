import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv


from ingestion.datajud_client import DatajudClient
from ingestion.core_ingestion import paginate

logger = logging.getLogger(__name__)
load_dotenv()

BRONZE_DIR = Path("data/bronze")


def ingest_tribunal(
    client: DatajudClient,
    tribunal: str,
    data_inicio: str,
    data_fim: str,
    output_dir: Path = BRONZE_DIR,
) -> None:
    dest = output_dir / tribunal / f"{data_inicio}_{data_fim}"
    dest.mkdir(parents=True, exist_ok=True)

    total = 0
    for page_num, hits in enumerate(paginate(client, tribunal, data_inicio, data_fim), start=1):
        file_path = dest / f"parte_{page_num:04d}.json"
        file_path.write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")
        total += len(hits)
        logger.info("Salvo: %s (%d processos)", file_path, len(hits))

    logger.info("Tribunal %s concluído: %d processos em %s", tribunal, total, dest)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    client = DatajudClient(api_key=os.environ["DATAJUD_API_KEY"])

    ingest_tribunal(client, tribunal="TJSC", data_inicio="2024-01-01", data_fim="2024-01-31")
    ingest_tribunal(client, tribunal="TJPR", data_inicio="2024-01-01", data_fim="2024-01-31")
