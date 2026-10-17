#!/usr/bin/env bash
# Deploy OpEx to Google Cloud Run as ONE service (web app + API + AI + simulator).
# Needs: the gcloud CLI, signed in (gcloud auth login), and a filled-in .env file.
# Usage:  ./deploy/deploy_cloud_run.sh  [region]      (default region: asia-south1 = Mumbai)
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${1:-asia-south1}"
SERVICE="opex"
PROJECT="$(grep -E '^GOOGLE_CLOUD_PROJECT=' .env | cut -d= -f2 | awk '{print $1}')"
if [ -z "$PROJECT" ]; then
  echo "Set GOOGLE_CLOUD_PROJECT in .env first (see AUDIT.md, step 4)."; exit 1
fi

echo "==> Enabling the Google Cloud APIs OpEx uses (safe to repeat)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com bigquery.googleapis.com storage.googleapis.com pubsub.googleapis.com \
  --project "$PROJECT"

echo "==> Turning .env into Cloud Run settings (secrets stay out of the image)"
ENV_FILE="$(mktemp)"
grep -E '^[A-Z_]+=' .env | grep -vE '^(GOOGLE_APPLICATION_CREDENTIALS|CORS_ORIGINS|ENV)=' | while IFS='=' read -r key value; do
  value="$(echo "$value" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+|[[:space:]]+$//g')"
  [ -n "$value" ] && printf '%s: "%s"\n' "$key" "$value"
done > "$ENV_FILE"
echo 'ENV: "production"' >> "$ENV_FILE"

echo "==> Building and deploying (about 5 minutes the first time)"
# max-instances=1 keeps one live-plant twin for everyone; raise it once readings come from real machines.
gcloud run deploy "$SERVICE" --source . --project "$PROJECT" --region "$REGION" \
  --allow-unauthenticated --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 \
  --timeout 300 --env-vars-file "$ENV_FILE"
rm -f "$ENV_FILE"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
echo "==> Done. OpEx is live at: $URL"
