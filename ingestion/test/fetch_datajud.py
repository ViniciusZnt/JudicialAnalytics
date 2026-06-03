import argparse
import os
from dotenv import load_dotenv
from ingestion.datajud_client import DatajudClient


load_dotenv()


def ultimo_movimento(movimentos: list[dict]) -> str:
    if not movimentos:
        return "sem movimentos"
    mais_recente = max(movimentos, key=lambda m: m.get("dataHora", ""))
    return mais_recente.get("nome", "nome não disponível")


def imprimir_processo(hit: dict) -> None:
    src = hit["_source"]
    numero    = src.get("numeroProcesso", "—")
    data      = src.get("dataAjuizamento", "—")[:10]
    classe    = (src.get("classeProcessual") or {}).get("nome", "—")
    tribunal  = src.get("tribunal", "—")
    movimento = ultimo_movimento(src.get("movimentos") or [])

    print(f"  {numero}")
    print(f"    Ajuizamento : {data}")
    print(f"    Tribunal    : {tribunal}")
    print(f"    Classe      : {classe}")
    print(f"    Últ. mov.   : {movimento}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca processos na API DataJud")
    parser.add_argument("--tribunal",  default="TJSP",       help="Sigla do tribunal (ex: TJSP, TJSC, TJPR)")
    parser.add_argument("--inicio",    default="2024-01-01", help="Data de início no formato YYYY-MM-DD")
    parser.add_argument("--fim",       default="2024-01-31", help="Data de fim no formato YYYY-MM-DD")
    args = parser.parse_args()

    api_key = os.environ.get("DATAJUD_API_KEY")
    if not api_key:
        raise SystemExit("DATAJUD_API_KEY não encontrada — configure o arquivo .env")

    client = DatajudClient(api_key=api_key)

    print(f"Buscando processos do {args.tribunal} ({args.inicio} → {args.fim})...\n")
    resposta = client.search_page(
        tribunal=args.tribunal,
        data_inicio=args.inicio,
        data_fim=args.fim,
    )

    hits  = resposta["hits"]["hits"]
    total = resposta["hits"]["total"]["value"]

    print(f"Total disponível: {total:,} processos")
    print(f"Exibindo os primeiros {len(hits)}:\n")
    print("-" * 60)

    for hit in hits:
        imprimir_processo(hit)


if __name__ == "__main__":
    main()
