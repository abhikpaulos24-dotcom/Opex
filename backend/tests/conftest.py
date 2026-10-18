import os
import tempfile

# Each test run gets its own throwaway database; no keys or cloud services are touched.
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()  # uploaded test files never land in the project
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = ""  # tests never use your real keys
os.environ["MASTER_ADMIN_EMAIL"] = "srihithapulapa1@gmail.com"
for name in ("GOOGLE_CLOUD_PROJECT", "BIGQUERY_DATASET", "GCS_BUCKET", "PUBSUB_ALERTS_TOPIC", "INGEST_API_KEY"):
    os.environ[name] = ""
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
os.environ["DEMO_MODE"] = "true"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_sign_in_limits():
    """Tests sign in far more often than any person would; start each one with a clean slate."""
    from app.api import auth

    auth._attempts.clear()
