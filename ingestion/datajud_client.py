import logging
import time
from collections.abc import Iterator

import requests

DEFAULT_BASE_URL = "https://api-publica.datajud.cnj.jus.br/"

logger = logging.getLogger(__name__)


class ApiResponseError(RuntimeError):
    pass


class BlockedResponseError(ApiResponseError):
    pass


class TransientApiError(ApiResponseError):
    pass


class DatajudClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"ApiKey {api_key}",
            "Content-Type": "application/json",
        })

    @staticmethod
    def _to_datajud_ts(data: str, fim: bool) -> str:
        """Converte 'YYYY-MM-DD' para o formato do campo dataAjuizamento ('YYYYMMDDHHMMSS').

        O campo dataAjuizamento na API DataJud é uma data no formato yyyyMMddHHmmss;
        consultar com data ISO ('2025-02-28') não casa e retorna 0 resultados.
        """
        compacta = data.replace("-", "")
        return compacta + ("235959" if fim else "000000")

    def search_page(self, tribunal: str, data_inicio: str, data_fim: str, search_after: list = None) -> dict:
        url = self.base_url + f"api_publica_{tribunal.lower()}/_search"

        body = {
            "size": 10000,
            "query": {
                "range": {
                    "dataAjuizamento": {
                        "gte": self._to_datajud_ts(data_inicio, fim=False),
                        "lte": self._to_datajud_ts(data_fim, fim=True),
                    }
                }
            },
            "sort": [
                {"@timestamp": {"order": "asc"}},
            ],
        }

        if search_after:
            body["search_after"] = search_after

        try:
            response = self.session.post(url, json=body, timeout=self.timeout)
            payload = self._safe_json(response)
        except requests.RequestException as exc:
            raise TransientApiError(f"Erro na requisição: {exc}") from exc

        if response.status_code == 200:
            return payload
        if response.status_code == 429:
            retry_after = response.headers.get("x-rate-limit-retry-after-seconds", "?")
            raise BlockedResponseError(f"Rate limit (429) — tente novamente em {retry_after}s")
        if response.status_code == 403:
            raise BlockedResponseError(self._extract_message(payload, response))
        if response.status_code >= 500:
            raise TransientApiError(self._extract_message(payload, response))
        raise ApiResponseError(self._extract_message(payload, response))

    def paginate(self, tribunal: str, data_inicio: str, data_fim: str) -> Iterator[list[dict]]:
        search_after = None
        page = 1

        while True:
            response = self.search_page(tribunal, data_inicio, data_fim, search_after=search_after)
            hits = response["hits"]["hits"]

            if not hits:
                logger.info("Paginação concluída após %d páginas.", page - 1)
                break

            logger.info("Página %d — %d processos recebidos.", page, len(hits))
            yield hits

            search_after = hits[-1]["sort"]
            page += 1
            time.sleep(0.5)

    @staticmethod
    def _safe_json(response):
        try:
            return response.json()
        except ValueError:
            return {"rawText": response.text}

    @staticmethod
    def _extract_message(payload, response):
        if isinstance(payload, dict):
            for key in ("developerMessage", "userMessage", "message", "rawText"):
                value = payload.get(key)
                if value:
                    return str(value)
        return f"HTTP {response.status_code}"
