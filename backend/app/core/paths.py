"""Every folder the app reads or writes, in one place."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
MODELS_DIR = ROOT / "models"
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR") or ROOT / "storage")  # local stand-in for Cloud Storage
FRONTEND_DIST = ROOT / "frontend" / "dist"
