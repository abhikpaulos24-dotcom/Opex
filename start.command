#!/usr/bin/env bash
# OpEx one-click start for macOS and Linux. Double-click this file (macOS) or run ./start.command
# It installs what it needs the first time (about 3-5 minutes), then opens OpEx in your browser.
set -e
cd "$(dirname "$0")"
echo ""
echo "  Starting OpEx - this window must stay open while you use the app."
echo ""

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "  Installing uv (a small tool that installs the right Python for OpEx)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

if [ ! -f .env ]; then
  echo "  Creating your settings file (.env)..."
  KEY="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48)"
  sed "s|^SECRET_KEY=.*|SECRET_KEY=$KEY|" .env.example > .env
fi

if [ ! -d .venv ]; then
  echo "  Setting up Python 3.12..."
  "$UV" venv .venv --python 3.12
fi
echo "  Installing OpEx's Python packages (first time only takes a few minutes)..."
"$UV" pip install --quiet --python .venv/bin/python -r backend/requirements.txt

if [ ! -f models/rul_model.joblib ]; then
  echo "  Training the AI models from the datasets (about 1 minute)..."
  (cd backend && ../.venv/bin/python -m pipeline.run_all)
fi

if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "  Building the web app..."
    (cd frontend && npm ci --no-audit --no-fund && npm run build)
  else
    echo "  The web app is not built and Node.js is not installed. Install Node.js 20+ from https://nodejs.org and try again."
    exit 1
  fi
fi

echo ""
echo "  OpEx is starting at http://localhost:8000  (press Ctrl+C here to stop it)"
echo ""
( sleep 5; (open http://localhost:8000 || xdg-open http://localhost:8000) >/dev/null 2>&1 ) &
exec .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
