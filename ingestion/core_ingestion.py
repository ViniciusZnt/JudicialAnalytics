import logging
import os
import time

from ingestion.datajud_client import DatajudClient, BlockedResponseError, TransientApiError
from ingestion.db import PostgresStore

logger = logging.getLogger(__name__)


def fetch_all_pages(client: DatajudClient, tribunal: str, data_inicio: str, data_fim: str, store: PostgresStore) -> None:
    search_after = None
    page = 1
    total_processos = 0

    while True:
        response = client.search_page(tribunal, data_inicio, data_fim, search_after=search_after)
        hits = response["hits"]["hits"]

        if not hits:
            break

        for hit in hits:
            store.append_hit(hit)

        total_processos += len(hits)
        logger.info("Página %d — %d processos acumulados.", page, total_processos)

        search_after = hits[-1]["sort"]
        page += 1
        time.sleep(0.5)

    store._flush()
    logger.info("Concluído: %d páginas, %d processos coletados.", page - 1, total_processos)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    store = PostgresStore(database_url=os.environ["DATABASE_URL"])
    store.connect()
    client = DatajudClient(api_key="cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==")
    try:
        fetch_all_pages(client, "TJSC", data_inicio="2024-01-01", data_fim="2024-01-31", store=store)
    finally:
        store.close()
