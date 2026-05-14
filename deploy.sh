#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — one-shot deploy of the Spotify → GCS Cloud Function
#
# Prerequisites:
#   1. gcloud CLI authenticated:   gcloud auth login
#   2. Project set:                gcloud config set project <YOUR_PROJECT_ID>
#   3. Spotify dev app credentials available in env (see step 3 below):
#        export SPOTIFY_CLIENT_ID=<your_client_id>
#        export SPOTIFY_CLIENT_SECRET=<your_client_secret>
#   4. GCS bucket exists:
#        gsutil mb -l us-central1 gs://dj-gig-tracks-2026
#   5. Function service account has Storage Object Admin on the bucket:
#        gcloud storage buckets add-iam-policy-binding gs://dj-gig-tracks-2026 \
#          --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
#          --role="roles/storage.objectAdmin"
# ---------------------------------------------------------------------------
set -euo pipefail

REGION="us-central1"
FUNCTION_NAME="download_playlist"
BUCKET="dj-gig-tracks-2026"

: "${SPOTIFY_CLIENT_ID:?Set SPOTIFY_CLIENT_ID before deploying}"
: "${SPOTIFY_CLIENT_SECRET:?Set SPOTIFY_CLIENT_SECRET before deploying}"

gcloud functions deploy "${FUNCTION_NAME}" \
  --gen2 \
  --runtime python311 \
  --region "${REGION}" \
  --source . \
  --entry-point download_playlist \
  --trigger-http \
  --allow-unauthenticated \
  --memory 8192MB \
  --cpu 2 \
  --timeout 3600s \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 5 \
  --set-env-vars "SPOTIFY_CLIENT_ID=${SPOTIFY_CLIENT_ID},SPOTIFY_CLIENT_SECRET=${SPOTIFY_CLIENT_SECRET},GCS_BUCKET=${BUCKET}"

echo ""
echo "✓ Deployed. Test with:"
echo "  curl -X POST \$(gcloud functions describe ${FUNCTION_NAME} --region ${REGION} --gen2 --format='value(serviceConfig.uri)') \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"playlist_url\": \"https://open.spotify.com/playlist/1HcikGvh5kGDTkzTLZX3U4?si=54776e8586dd499f\"}'"
