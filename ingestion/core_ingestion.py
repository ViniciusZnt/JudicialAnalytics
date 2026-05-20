import logging
import time
from collections.abc import Iterator

from ingestion.datajud_client import DatajudClient

logger = logging.getLogger(__name__)


def paginate(
    client: DatajudClient,
    tribunal: str,
    data_inicio: str,
    data_fim: str,
) -> Iterator[list[dict]]:
    """Retorna uma página de hits por vez até a API não retornar mais resultados."""
    search_after = None
    page = 1

    while True:
        response = client.search_page(tribunal, data_inicio, data_fim, search_after=search_after)
        hits = response["hits"]["hits"]

        if not hits:
            logger.info("Paginação concluída após %d páginas.", page - 1)
            break

        logger.info("Página %d — %d processos recebidos.", page, len(hits))
        yield hits

        search_after = hits[-1]["sort"] # Cursor do ElasticSearch
        page += 1
        time.sleep(0.5)
