import sys

if sys.version_info < (3, 11):  # noqa: UP036  (this check exists for people on an old Python)
    raise SystemExit(
        f"OpEx needs Python 3.11 or newer, but this is Python {sys.version_info.major}.{sys.version_info.minor}.\n"
        "Install Python 3.12 (https://www.python.org/downloads/ or `brew install python@3.12`), then make a new "
        "environment with it:\n  python3.12 -m venv new-env && source new-env/bin/activate && "
        "pip install -r requirements.txt"
    )
