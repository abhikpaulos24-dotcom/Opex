"""Fetch the public datasets into data/raw/. Files that already exist are skipped.

Sources (all free for research use - licences in README > Data sources):
  AI4I 2020         UCI ML Repository, CC BY 4.0
  NASA C-MAPSS      NASA Prognostics Data Repository, public domain (FD001 subset)
  Azure PdM         Microsoft Azure AI Gallery sample (GitHub mirror)
  Zenodo 17855209   OEE & downtime of a real production line, CC BY 4.0
"""

import io
import logging
import urllib.request
import zipfile

from .common import RAW_DIR

log = logging.getLogger("pipeline.download")

AZURE_MIRROR = (
    "https://raw.githubusercontent.com/ashishpatel26/"
    "Predictive_Maintenance_using_Machine-Learning_Microsoft_Casestudy/master/data/"
)
ZENODO = "https://zenodo.org/records/17855209/files/"

FILES = {
    "ai4i/ai4i2020.csv": (
        "zip",
        "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip",
    ),
    "azure_pdm/PdM_telemetry.csv": ("plain", AZURE_MIRROR + "PdM_telemetry.csv"),
    "azure_pdm/PdM_failures.csv": ("plain", AZURE_MIRROR + "PdM_failures.csv"),
    "azure_pdm/PdM_maint.csv": ("plain", AZURE_MIRROR + "PdM_maint.csv"),
    "azure_pdm/PdM_errors.csv": ("plain", AZURE_MIRROR + "PdM_errors.csv"),
    "azure_pdm/PdM_machines.csv": ("plain", AZURE_MIRROR + "PdM_machines.csv"),
    "zenodo_oee/OEEdataset.csv": ("plain", ZENODO + "OEEdataset.csv?download=1"),
    "zenodo_oee/OEEdataset_afterLSS.csv": ("plain", ZENODO + "OEEdataset_afterLSS.csv?download=1"),
    "zenodo_oee/DowntimeDataset.csv": ("plain", ZENODO + "DowntimeDataset.csv?download=1"),
}
# NASA C-MAPSS needs a manual download (the NASA portal has no stable direct link):
# https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data -> copy train_FD001.txt,
# test_FD001.txt and RUL_FD001.txt into data/raw/cmapss/. They ship with this repo.


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "opex-pipeline"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def main() -> None:
    for relative, (kind, url) in FILES.items():
        target = RAW_DIR / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s", relative)
        try:
            payload = _fetch(url)
        except Exception as exc:  # network trouble should not stop the rest
            log.warning("could not download %s: %s", relative, exc)
            continue
        if kind == "zip":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                target.write_bytes(archive.read(target.name))
        else:
            target.write_bytes(payload)

    missing = [
        p
        for p in ("cmapss/train_FD001.txt", "cmapss/test_FD001.txt", "cmapss/RUL_FD001.txt")
        if not (RAW_DIR / p).exists()
    ]
    if missing:
        log.warning("NASA C-MAPSS files missing: %s (see comment in download_data.py)", missing)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
