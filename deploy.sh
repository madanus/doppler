#!/usr/bin/env bash
# Doppler GCP Deployment & Infrastructure Creation Script
# Fully automated, serverless, scale-to-zero cost.

set -e

# Configuration
REGION="us-central1"
BILLING_ACCOUNT_ID="01DAF2-20428F-DEE55E" # TouchTap Technologies active open billing account

# Generate a unique project ID to avoid collisions
RANDOM_ID=$(jot -r 1 10000 99999 2>/dev/null || echo $((10000 + RANDOM % 90000)))
PROJECT_ID="doppler-self-learning-${RANDOM_ID}"

echo -e "\033[1;35m====================================================\033[0m"
echo -e "\033[1;35m       DOPPLER GCP AUTOMATED SERVERLESS DEPLOY       \033[0m"
echo -e "\033[1;35m====================================================\033[0m"
echo -e "Project ID generated: \033[1;36m${PROJECT_ID}\033[0m"
echo -e "Region:               \033[1;36m${REGION}\033[0m"
echo -e "Billing Account ID:   \033[1;36m${BILLING_ACCOUNT_ID}\033[0m"
print_warning() {
  echo -e "\033[1;33m$1\033[0m"
}

# 1. Create Google Cloud Project
echo -e "\n\033[1;34m[1/6] Creating new Google Cloud project...\033[0m"
gcloud projects create "${PROJECT_ID}" --name="Doppler AI Self Learning"

# 2. Link Billing Account (Ensures Artifact Registry and Cloud Build function)
echo -e "\n\033[1;34m[2/6] Linking billing account to the new project...\033[0m"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"

# 3. Enable Required Serverless APIs
echo -e "\n\033[1;34m[3/6] Enabling APIs: Cloud Run, Cloud Build, Artifact Registry...\033[0m"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# 4. Create Artifact Registry Repository for Docker container
echo -e "\n\033[1;34m[4/6] Creating us-central1 Docker repository in Artifact Registry...\033[0m"
gcloud artifacts repositories create doppler-repo \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Artifact Registry for Doppler AI self-learning server" \
  --project="${PROJECT_ID}"

# 5. Build Container on the Cloud using GCP Cloud Build (No local Docker required)
echo -e "\n\033[1;34m[5/6] Submitting container build to Cloud Build...\033[0m"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/doppler-repo/doppler-server:latest"
gcloud builds submit \
  --tag "${IMAGE_TAG}" \
  --project="${PROJECT_ID}" \
  doppler-server/

# 6. Deploy to Google Cloud Run (Serverless, Scale-to-Zero, 100% Free under quotas)
echo -e "\n\033[1;34m[6/6] Deploying Doppler control plane to Cloud Run...\033[0m"
gcloud run deploy doppler-server \
  --image="${IMAGE_TAG}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="GAE_ENV=production" \
  --project="${PROJECT_ID}"

# Fetch the live service URL
SERVICE_URL=$(gcloud run services describe doppler-server --platform=managed --region="${REGION}" --format="value(status.url)" --project="${PROJECT_ID}")

echo -e "\n\033[1;32m====================================================\033[0m"
echo -e "\033[1;32m   🎉 DOPPLER SERVERLESS CONTROL PLANE DEPLOYED!     \033[0m"
echo -e "\033[1;32m====================================================\033[0m"
echo -e "Project ID:        \033[1;36m${PROJECT_ID}\033[0m"
echo -e "Service URL:       \033[1;32m${SERVICE_URL}\033[0m"
echo -e "Client config CMD: \033[1;33mexport DOPPLER_SERVER_URL=\"${SERVICE_URL}\"\033[0m"
echo -e "Test connection:   \033[1;33mcurl ${SERVICE_URL}/\033[0m"
echo -e "Run Client Status: \033[1;33mpython3 doppler_client.py status --server \"${SERVICE_URL}\"\033[0m"
echo -e "\033[1;32m====================================================\033[0m"
