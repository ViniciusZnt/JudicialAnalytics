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


class RateLimitError(TransientApiError):
    """429 — erro transiente que carrega o tempo sugerido de espera (retry-after)."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class DatajudClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
        pausa_entre_paginas: float = 1.0,
        max_retentativas_pagina: int = 5,
        espera_base_retry: int = 10,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.pausa_entre_paginas = pausa_entre_paginas
        self.max_retentativas_pagina = max_retentativas_pagina
        self.espera_base_retry = espera_base_retry
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"ApiKey {api_key}",
            "Content-Type": "application/json",
        })

    def search_page(self, tribunal: str, data_inicio: str, data_fim: str, search_after: list = None) -> dict:
        url = self.base_url + f"api_publica_{tribunal.lower()}/_search"

        body = {
            # size pequeno é o que mantém a resposta abaixo do gateway de ~60s da API.
            # Em testes: size 10000 → 504 (60s); 1000 → 30-50s e às vezes 504; 500 → ~9,5s.
            # Aumentar o size pra fazer menos requests NÃO ajuda: troca 429 por 504.
            "size": 500,
            "_source": [
                "numeroProcesso",
                "tribunal",
                "grau",
                "dataAjuizamento",
                "classe",
                "orgaoJulgador",
                "movimentos",
                "assuntos",
                "nivelSigilo",
            ],
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
            retry_after_raw = response.headers.get("x-rate-limit-retry-after-seconds")
            try:
                retry_after = int(retry_after_raw)
            except (TypeError, ValueError):
                retry_after = None
            raise RateLimitError(
                f"Rate limit (429) — tente novamente em {retry_after_raw or '?'}s",
                retry_after=retry_after,
            )
        if response.status_code == 403:
            raise BlockedResponseError(self._extract_message(payload, response))
        if response.status_code >= 500:
            raise TransientApiError(self._extract_message(payload, response))
        raise ApiResponseError(self._extract_message(payload, response))

    def paginate(self, tribunal: str, data_inicio: str, data_fim: str) -> Iterator[list[dict]]:
        search_after = None
        page = 1

        while True:
            # Retenta a MESMA página (mesmo cursor search_after) em caso de erro
            # transiente, preservando o progresso das páginas anteriores em vez de
            # reiniciar a paginação do zero.
            response = self._buscar_pagina_com_retry(tribunal, data_inicio, data_fim, search_after, page)
            hits = response["hits"]["hits"]

            if not hits:
                logger.info("Paginação concluída após %d páginas.", page - 1)
                break

            logger.info("Página %d — %d processos recebidos.", page, len(hits))
            yield hits

            search_after = hits[-1]["sort"]
            page += 1
            time.sleep(self.pausa_entre_paginas)

    def _buscar_pagina_com_retry(self, tribunal, data_inicio, data_fim, search_after, page) -> dict:
        for tentativa in range(1, self.max_retentativas_pagina + 1):
            try:
                return self.search_page(tribunal, data_inicio, data_fim, search_after=search_after)
            except TransientApiError as exc:
                if tentativa == self.max_retentativas_pagina:
                    logger.error(
                        "Página %d falhou após %d tentativas — propagando erro. %s",
                        page, self.max_retentativas_pagina, exc,
                    )
                    raise

                if isinstance(exc, RateLimitError) and exc.retry_after:
                    espera = exc.retry_after
                else:
                    espera = self.espera_base_retry * tentativa

                logger.warning(
                    "Página %d — erro transiente na tentativa %d/%d, aguardando %ds e mantendo o cursor. %s",
                    page, tentativa, self.max_retentativas_pagina, espera, exc,
                )
                time.sleep(espera)
        raise RuntimeError("inalcançável")

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

    @staticmethod
    def _to_datajud_ts(data: str, fim: bool) -> str:
        """Converte 'YYYY-MM-DD' para o formato do campo dataAjuizamento ('YYYYMMDDHHMMSS').

        O campo dataAjuizamento na API DataJud é uma data no formato yyyyMMddHHmmss;
        consultar com data ISO ('2025-02-28') não casa e retorna 0 resultados.
        """
        compacta = data.replace("-", "")
        return compacta + ("235959" if fim else "000000")
