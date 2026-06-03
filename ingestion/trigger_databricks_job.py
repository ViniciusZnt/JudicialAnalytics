import logging
import os

import requests

logger = logging.getLogger(__name__)

JOB_ID = 0  # preencher no M7


def disparar() -> None:
    if not JOB_ID:
        logger.info("JOB_ID não configurado — trigger ignorado")
        return

    host  = os.environ["DATABRICKS_HOST"]
    token = os.environ["DATABRICKS_TOKEN"]

    resp = requests.post(
        f"{host}/api/2.1/jobs/run-now",
        headers={"Authorization": f"Bearer {token}"},
        json={"job_id": JOB_ID},
        timeout=30,
    )
    resp.raise_for_status()
    logger.info("Job %d disparado — run_id: %s", JOB_ID, resp.json()["run_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    disparar()