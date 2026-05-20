import requests

DEFAULT_BASE_URL = "https://api-publica.datajud.cnj.jus.br/"

TRIBUNAIS = {
    "TJSC": "api_publica_tjsc/_search",
    "TJPR": "api_publica_tjpr/_search",
}

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

    def search_page(self, tribunal: str, data_inicio: str, data_fim: str, search_after: list = None) -> dict:
        url = self.base_url + TRIBUNAIS[tribunal]

        body = {
            "size": 100,
            "query": {
                "range": {
                    "dataAjuizamento": {
                        "gte": data_inicio,
                        "lte": data_fim,
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