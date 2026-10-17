"""Run the whole offline pipeline in order. Takes about 30 seconds (2 minutes with Azure telemetry).

cd backend && python -m pipeline.run_all
"""

import logging
import time

from . import (
    build_factory_memory,
    calibrate_simulation,
    download_data,
    prepare_datasets,
    train_failure_model,
    train_precursor_model,
    train_rul_model,
)

log = logging.getLogger("pipeline")

STEPS = [
    ("Download public datasets", download_data.main),
    ("Clean data + quality report", prepare_datasets.main),
    ("Train failure-mode model (AI4I)", train_failure_model.main),
    ("Train remaining-life model (NASA C-MAPSS)", train_rul_model.main),
    ("Train component precursor model (Azure PdM)", train_precursor_model.main),
    ("Calibrate the 5-year simulator", calibrate_simulation.main),
    ("Build factory memory", build_factory_memory.main),
]


def main() -> None:
    for number, (title, step) in enumerate(STEPS, start=1):
        started = time.perf_counter()
        log.info("[%d/%d] %s", number, len(STEPS), title)
        step()
        log.info("      done in %.1fs", time.perf_counter() - started)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
