"""Optional: copy OpEx data into BigQuery for long-term analysis (Looker Studio, SQL).

Uses batch load jobs only, never streaming, so it works in the free BigQuery sandbox
(no billing account; tables there expire after 60 days). Does nothing until
BIGQUERY_DATASET and GOOGLE_CLOUD_PROJECT are set.
"""

import logging
import threading

from app.core.config import get_settings

log = logging.getLogger(__name__)


def enabled() -> bool:
    s = get_settings()
    return bool(s.bigquery_dataset and s.google_cloud_project)


def _load(client, table: str, rows: list[dict], replace: bool) -> None:
    from google.cloud import bigquery

    s = get_settings()
    config = bigquery.LoadJobConfig(autodetect=True, write_disposition="WRITE_TRUNCATE" if replace else "WRITE_APPEND")
    client.load_table_from_json(
        rows, f"{s.google_cloud_project}.{s.bigquery_dataset}.{table}", job_config=config
    ).result()
    log.info("BigQuery: loaded %d rows into %s", len(rows), table)


def _client():
    from google.cloud import bigquery

    s = get_settings()
    client = bigquery.Client(project=s.google_cloud_project, location=s.bigquery_location)
    dataset = bigquery.Dataset(f"{s.google_cloud_project}.{s.bigquery_dataset}")
    dataset.location = s.bigquery_location
    client.create_dataset(dataset, exists_ok=True)
    return client


def append_in_background(table: str, rows: list[dict]) -> None:
    """Fire-and-forget append (used after each simulation run)."""
    if not enabled() or not rows:
        return

    def run() -> None:
        try:
            _load(_client(), table, rows, replace=False)
        except Exception as exc:  # analytics export must never break the app
            log.warning("BigQuery load into %s failed: %s", table, exc)

    threading.Thread(target=run, daemon=True).start()


def replace_tables(tables: dict[str, list[dict]]) -> dict[str, int]:
    """Overwrite each table with a fresh snapshot. Returns rows written per table."""
    client = _client()
    written = {}
    for table, rows in tables.items():
        if rows:
            _load(client, table, rows, replace=True)
        written[table] = len(rows)
    return written


def console_url() -> str:
    s = get_settings()
    return f"https://console.cloud.google.com/bigquery?project={s.google_cloud_project}&ws=!1m4!1m3!3m2!1s{s.google_cloud_project}!2s{s.bigquery_dataset}"
