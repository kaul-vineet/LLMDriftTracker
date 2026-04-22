#!/usr/bin/env bash
# ── ĀSHOKĀ · Azure Container Apps deployment ──────────────────────────────────
#
# This script provisions all Azure infrastructure and deploys the āshokā agent
# and dashboard as Azure Container Apps sharing a single image and Azure Files
# volume for persistent data.
#
# What gets created
# ──────────────────
#   Resource Group             ashoka-rg
#   Container Registry (ACR)   ashokaacr  (built once, both apps pull from it)
#   Container Apps Environment ashoka-env (Consumption plan — pay per use)
#   Storage Account            ashokastore
#   Azure Files — data share   ashoka-data       → mounted at /app/data
#   Azure Files — config share ashoka-config     → mounted at /app/config
#   Container App              ashoka-agent      (background process, no ingress)
#   Container App              ashoka-dashboard  (public HTTPS on port 8501)
#
# Architecture diagram
# ─────────────────────
#                ┌─────────────────────────────────────────────┐
#                │          Azure Container Apps Environment    │
#                │                                             │
#   Internet ───▶│  ashoka-dashboard  (HTTPS, port 8501)       │
#                │       │  reads /app/data  /app/config       │
#                │       │                                     │
#                │  ashoka-agent  (no ingress, always-on)      │
#                │       │  reads /app/data  /app/config       │
#                └───────┼─────────────────────────────────────┘
#                        │
#              ┌─────────┴──────────────────┐
#              │      Azure Files Shares     │
#              │  ashoka-data   (read-write) │  ← eval runs, logs, MSAL cache
#              │  ashoka-config (read-write) │  ← config.json (Setup saves here)
#              └────────────────────────────┘
#
# Why two shares?
# ────────────────
# Azure Container Apps mounts an entire Azure Files share at a given path.
# • ashoka-data   mounted at /app/data    — agent writes run results here
# • ashoka-config mounted at /app/config  — holds config.json; Setup page can save
#   changes which the agent picks up on its next poll cycle.
#   CONFIG_PATH=/app/config/config.json tells both containers where to read it.
#
# Config.json is uploaded to the config share BEFORE containers start so both apps
# find their settings on first boot.  If the share is empty, the Setup page will
# show a "No config.json" warning and let you fill everything in from the browser.
#
# MSAL token cache
# ─────────────────
# The MSAL token cache lives at /app/data/agent/msal_token_cache.json (inside the
# data share).  After deploying, open the dashboard URL, go to Setup → Authentication,
# and click Sign In.  The device flow writes the token cache to the share so both
# the agent and dashboard can authenticate to Dataverse without re-prompting.
#
# Scaling
# ────────
# Both apps are pinned to minReplicas=1 maxReplicas=1 so there is exactly one
# instance of each at all times.  The agent must be single-instance to avoid
# duplicate eval runs.  Scale the dashboard independently if needed, but be aware
# that multiple dashboard replicas would all share the same MSAL cache file (safe
# for reads, potentially racy for writes during the Setup auth flow).
#
# Usage
# ──────
#   1. Edit the "── CONFIGURATION ──" section below.
#   2. Ensure config.json exists in the repo root with your real values.
#   3. Log in:  az login
#   4. Run:     bash docker/azure-deploy.sh
#
# Re-running the script is safe — it uses --if-not-exists / --only-show-errors
# so existing resources are skipped and only the image push + container app update
# runs on subsequent executions.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── CONFIGURATION — edit these ───────────────────────────────────────────────

RESOURCE_GROUP="ashoka-rg"
LOCATION="eastus"                 # az account list-locations -o table
ACR_NAME="ashokaacr"             # Must be globally unique, 5-50 alphanumeric chars
STORAGE_ACCOUNT="ashokastore"    # Must be globally unique, 3-24 lowercase alphanumeric
ENV_NAME="ashoka-env"
APP_AGENT="ashoka-agent"
APP_DASHBOARD="ashoka-dashboard"
IMAGE_NAME="ashoka"
IMAGE_TAG="latest"

DATA_SHARE="ashoka-data"
CONFIG_SHARE="ashoka-config"

# CPU and memory for each container app.
# Consumption plan allows: 0.25/0.5, 0.5/1, 0.75/1.5, 1/2, 1.25/2.5, 1.5/3, 1.75/3.5, 2/4
AGENT_CPU="0.5"
AGENT_MEM="1.0Gi"
DASHBOARD_CPU="0.5"
DASHBOARD_MEM="1.0Gi"

# Path to config.json on your local machine (relative to repo root).
CONFIG_JSON_LOCAL="config.json"

# ── END CONFIGURATION ────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          ĀSHOKĀ · Azure Container Apps Deploy        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────────────
echo "▶ Checking prerequisites..."

if ! command -v az &>/dev/null; then
  echo "✗  Azure CLI not found. Install: https://aka.ms/installazurecliwindows"
  exit 1
fi

az extension add --name containerapp --only-show-errors --upgrade 2>/dev/null || true

if [ ! -f "$CONFIG_JSON_LOCAL" ]; then
  echo "⚠  $CONFIG_JSON_LOCAL not found."
  echo "   Copy config.example.json → config.json and fill in your values first."
  echo "   Or deploy without it and configure everything from the Setup page after launch."
  echo ""
  read -rp "   Continue without uploading config.json? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

SUBSCRIPTION=$(az account show --query id -o tsv)
echo "   Subscription: $SUBSCRIPTION"
echo ""

# ── Resource Group ───────────────────────────────────────────────────────────
echo "▶ Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── Azure Container Registry ─────────────────────────────────────────────────
echo "▶ Container registry: $ACR_NAME"
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none 2>/dev/null || echo "   (already exists)"

ACR_LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer -o tsv)

ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "passwords[0].value" -o tsv)

# ── Build and push image ──────────────────────────────────────────────────────
# Build locally and push, OR use ACR Tasks to build in the cloud (no Docker required).
#
# Option A (default) — local Docker build:
echo "▶ Building and pushing image to $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
echo "   (Building from repo root using docker/Dockerfile)"
az acr login --name "$ACR_NAME" --output none

# Change to repo root (script is in docker/, but build context must be repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

docker build \
  --file "$SCRIPT_DIR/Dockerfile" \
  --tag "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  "$REPO_ROOT"

docker push "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"

# Option B — cloud build (uncomment to build without local Docker):
# az acr build \
#   --registry "$ACR_NAME" \
#   --image "$IMAGE_NAME:$IMAGE_TAG" \
#   --file "$SCRIPT_DIR/Dockerfile" \
#   "$REPO_ROOT"

echo "   ✓ Image: $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"

# ── Storage Account + Azure Files ────────────────────────────────────────────
echo "▶ Storage account: $STORAGE_ACCOUNT"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output none 2>/dev/null || echo "   (already exists)"

STORAGE_KEY=$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT" \
  --query "[0].value" -o tsv)

echo "▶ Azure Files shares: $DATA_SHARE, $CONFIG_SHARE"
az storage share create \
  --name "$DATA_SHARE" \
  --account-name "$STORAGE_ACCOUNT" \
  --account-key "$STORAGE_KEY" \
  --output none 2>/dev/null || echo "   (data share already exists)"

az storage share create \
  --name "$CONFIG_SHARE" \
  --account-name "$STORAGE_ACCOUNT" \
  --account-key "$STORAGE_KEY" \
  --output none 2>/dev/null || echo "   (config share already exists)"

# Upload config.json to the config share so containers find it on first boot.
if [ -f "$CONFIG_JSON_LOCAL" ]; then
  echo "▶ Uploading config.json to Azure Files config share..."
  az storage file upload \
    --share-name "$CONFIG_SHARE" \
    --source "$CONFIG_JSON_LOCAL" \
    --path "config.json" \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --output none
  echo "   ✓ config.json uploaded to share $CONFIG_SHARE/config.json"
  echo "   ⚠  After the Setup page saves new settings, the share copy is updated."
  echo "      Agent picks up changes on its next poll cycle (no restart needed)."
fi

# ── Container Apps Environment ────────────────────────────────────────────────
echo "▶ Container Apps environment: $ENV_NAME"
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none 2>/dev/null || echo "   (already exists)"

# Link the two Azure Files shares to the environment so container apps can mount them.
echo "▶ Linking storage shares to environment..."
az containerapp env storage set \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-name "ashoka-data-storage" \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name "$DATA_SHARE" \
  --access-mode ReadWrite \
  --output none

az containerapp env storage set \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-name "ashoka-config-storage" \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name "$CONFIG_SHARE" \
  --access-mode ReadWrite \
  --output none

echo "   ✓ Storage shares linked"

# ── Container app YAML helper ─────────────────────────────────────────────────
# ACA storage volume mounts require the full container spec in YAML.
# We generate it inline with real values and apply via 'az containerapp create --yaml'.
#
# Why YAML for mounts?  The CLI flags --volume / --volumeMount are not yet available
# for Azure Files in all CLI versions; the YAML spec is stable and version-agnostic.

ENV_ID=$(az containerapp env show \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

# ── Deploy: ashoka-agent ──────────────────────────────────────────────────────
echo "▶ Deploying container app: $APP_AGENT"
cat > /tmp/ashoka-agent.yaml <<YAML
location: ${LOCATION}
type: Microsoft.App/containerApps
name: ${APP_AGENT}
properties:
  environmentId: ${ENV_ID}
  configuration:
    # No ingress — agent is a background process, not reachable from outside.
    ingress: null
    registries:
    - server: ${ACR_LOGIN_SERVER}
      username: ${ACR_NAME}
      passwordSecretRef: acr-password
    secrets:
    - name: acr-password
      value: "${ACR_PASSWORD}"
  template:
    containers:
    - name: ${APP_AGENT}
      image: ${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}
      command:
      - python
      - -m
      - agent.main
      env:
      # STORE_DIR tells the agent where to write eval data, logs, and MSAL cache.
      # Must match the mountPath for the data volume below.
      - name: STORE_DIR
        value: /app/data
      # CONFIG_PATH tells the agent where to read config.json.
      # Must match mountPath/filename for the config volume below.
      - name: CONFIG_PATH
        value: /app/config/config.json
      resources:
        cpu:    ${AGENT_CPU}
        memory: ${AGENT_MEM}
      volumeMounts:
      - volumeName: data-vol
        mountPath: /app/data
      - volumeName: config-vol
        mountPath: /app/config
    volumes:
    - name: data-vol
      storageType: AzureFile
      storageName: ashoka-data-storage    # Must match the storage-name set in env storage set above
    - name: config-vol
      storageType: AzureFile
      storageName: ashoka-config-storage
    scale:
      minReplicas: 1   # Always-on — agent must be running to detect model changes
      maxReplicas: 1   # Single instance to avoid duplicate eval runs
YAML

az containerapp create \
  --resource-group "$RESOURCE_GROUP" \
  --yaml /tmp/ashoka-agent.yaml \
  --output none

echo "   ✓ $APP_AGENT deployed"

# ── Deploy: ashoka-dashboard ──────────────────────────────────────────────────
echo "▶ Deploying container app: $APP_DASHBOARD"
cat > /tmp/ashoka-dashboard.yaml <<YAML
location: ${LOCATION}
type: Microsoft.App/containerApps
name: ${APP_DASHBOARD}
properties:
  environmentId: ${ENV_ID}
  configuration:
    ingress:
      external: true          # Publicly accessible HTTPS URL
      targetPort: 8501
      transport: http         # Streamlit uses HTTP/1.1 + WebSocket upgrade
      allowInsecure: false
      # To restrict access to your corporate network, add IP security restrictions:
      # ipSecurityRestrictions:
      # - action: Allow
      #   ipAddressRange: "203.0.113.0/24"
      #   name: corp-network
    registries:
    - server: ${ACR_LOGIN_SERVER}
      username: ${ACR_NAME}
      passwordSecretRef: acr-password
    secrets:
    - name: acr-password
      value: "${ACR_PASSWORD}"
  template:
    containers:
    - name: ${APP_DASHBOARD}
      image: ${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}
      command:
      - streamlit
      - run
      - dashboard/app.py
      - --server.port=8501
      - --server.address=0.0.0.0
      - --server.headless=true
      - --server.fileWatcherType=none
      env:
      - name: STORE_DIR
        value: /app/data
      - name: CONFIG_PATH
        value: /app/config/config.json
      resources:
        cpu:    ${DASHBOARD_CPU}
        memory: ${DASHBOARD_MEM}
      volumeMounts:
      - volumeName: data-vol
        mountPath: /app/data
      - volumeName: config-vol
        mountPath: /app/config
    volumes:
    - name: data-vol
      storageType: AzureFile
      storageName: ashoka-data-storage
    - name: config-vol
      storageType: AzureFile
      storageName: ashoka-config-storage
    scale:
      minReplicas: 1
      maxReplicas: 1
YAML

az containerapp create \
  --resource-group "$RESOURCE_GROUP" \
  --yaml /tmp/ashoka-dashboard.yaml \
  --output none

echo "   ✓ $APP_DASHBOARD deployed"

# ── Output ───────────────────────────────────────────────────────────────────
DASHBOARD_URL=$(az containerapp show \
  --name "$APP_DASHBOARD" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                  Deploy complete ✓                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Dashboard:  https://${DASHBOARD_URL}"
echo "  Resource group: $RESOURCE_GROUP"
echo ""
echo "  Next steps"
echo "  ──────────"
echo "  1. Open the dashboard URL above."
echo "  2. Go to Setup → Authentication → Sign In."
echo "     Complete device-code auth to write the MSAL token cache to Azure Files."
echo "     The agent will pick it up automatically."
echo "  3. Go to Setup and verify the READY TO START indicator is green."
echo "  4. Force an eval from the ĀSHOKĀ page to confirm end-to-end connectivity."
echo ""
echo "  Tail logs"
echo "  ─────────"
echo "  Agent:     az containerapp logs show -n $APP_AGENT -g $RESOURCE_GROUP --follow"
echo "  Dashboard: az containerapp logs show -n $APP_DASHBOARD -g $RESOURCE_GROUP --follow"
echo ""
echo "  Update image (after code change)"
echo "  ─────────────────────────────────"
echo "  Re-run this script.  It will rebuild, push, and update both container apps."
echo "  Or manually:"
echo "    docker build -f docker/Dockerfile -t $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG ."
echo "    docker push $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
echo "    az containerapp update -n $APP_AGENT     -g $RESOURCE_GROUP --image $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
echo "    az containerapp update -n $APP_DASHBOARD -g $RESOURCE_GROUP --image $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"
echo ""
echo "  Tear down everything"
echo "  ─────────────────────"
echo "  az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo ""
