#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Setup GitHub Actions OIDC (Federated Credential) for Azure.

This script creates/reuses:
- Entra app registration + service principal
- Federated identity credential for GitHub Actions OIDC
- Optional RBAC role assignment

Prerequisites:
- Azure CLI (az) installed
- az login already done
- (Optional) GitHub CLI (gh) installed + authenticated when using --configure-github

Examples:
  # From a repo checkout (auto-detect owner/repo via git remote):
  ./scripts/setup_github_actions_oidc.sh \
    --branch main \
    --resource-group <rg>

  # Explicit owner/repo:
  ./scripts/setup_github_actions_oidc.sh \
    --owner yourname --repo yourrepo --branch main \
    --resource-group <rg>

  # Also grant Static Web Apps permissions (same resource group):
  ./scripts/setup_github_actions_oidc.sh \
    --resource-group <rg> --enable-swa

  # Override SWA role name (optional):
  ./scripts/setup_github_actions_oidc.sh \
    --resource-group <rg> --enable-swa --swa-role "Contributor"

Notes:
- For labs, we recommend using GitHub Repository Variables (vars) instead of Secrets.
- By default, the federated credential is limited to ref:refs/heads/<branch>.
  That matches workflow_dispatch runs on that branch.
EOF
}

print_cli_install_help() {
  cat <<'EOF' >&2
Missing required CLI.

Install guides:
- Azure CLI:  https://learn.microsoft.com/cli/azure/install-azure-cli
- GitHub CLI: https://cli.github.com/

Quick install (Ubuntu/Debian examples):
- Azure CLI:
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
- GitHub CLI:
  sudo apt-get update && sudo apt-get install -y gh

Windows (PowerShell, using winget):
  winget install -e --id Microsoft.AzureCLI
  winget install -e --id GitHub.cli

Tip:
- On Windows, you can also use ./scripts/setup_github_actions_oidc.ps1
EOF
}

print_manual_vars_instructions() {
  cat <<EOF

== Next step: set GitHub Repository Variables (recommended for labs) ==
In your GitHub repo: Settings → Secrets and variables → Actions → Variables

Create these Variables:
  AZURE_CLIENT_ID=${APP_ID}
  AZURE_TENANT_ID=${TENANT_ID}
  AZURE_SUBSCRIPTION_ID=${SUBSCRIPTION_ID}

Also set (per-student):
  AZURE_AI_PROJECT_ENDPOINT=<your-foundry-project-endpoint>
  AZURE_AI_MODEL_DEPLOYMENT_NAME=<your-model-deployment>

Tip:
- If you want this script to auto-write Variables, re-run with: --configure-github
EOF
}

APP_NAME="gcr-ai-tour-gha-oidc"
OWNER=""
REPO=""
BRANCH="main"
RESOURCE_GROUP=""
SUBSCRIPTION_ID=""
TENANT_ID=""
ROLE_NAME="Cognitive Services User"
SWA_ROLE_OVERRIDE=""
ENABLE_SWA="false"
CONFIGURE_GITHUB="false"
GITHUB_REPO=""
AI_PROJECT_ENDPOINT=""
AI_MODEL_DEPLOYMENT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --app-name)
      APP_NAME="$2"; shift 2 ;;
    --owner)
      OWNER="$2"; shift 2 ;;
    --repo)
      REPO="$2"; shift 2 ;;
    --branch)
      BRANCH="$2"; shift 2 ;;
    --resource-group)
      RESOURCE_GROUP="$2"; shift 2 ;;
    --subscription-id)
      SUBSCRIPTION_ID="$2"; shift 2 ;;
    --tenant-id)
      TENANT_ID="$2"; shift 2 ;;
    --role)
      ROLE_NAME="$2"; shift 2 ;;
    --enable-swa)
      ENABLE_SWA="true"; shift 1 ;;
    --swa-role)
      SWA_ROLE_OVERRIDE="$2"; shift 2 ;;
    --configure-github)
      CONFIGURE_GITHUB="true"; shift 1 ;;
    --github-repo)
      GITHUB_REPO="$2"; shift 2 ;;
    --ai-project-endpoint)
      AI_PROJECT_ENDPOINT="$2"; shift 2 ;;
    --ai-model-deployment-name)
      AI_MODEL_DEPLOYMENT_NAME="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -eq 0 ]]; then
  echo "ERROR: Do not run this script with sudo/root." >&2
  echo "Azure CLI (az) and GitHub CLI (gh) authentication are per-user." >&2
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "Re-run as the original user: ${SUDO_USER}" >&2
    echo "  ./scripts/setup_github_actions_oidc.sh [args...]" >&2
    echo "If you used 'sudo bash ...', remove sudo and run it normally." >&2
  else
    echo "Re-run as a normal user (non-root) who has run: az login (and gh auth login if using --configure-github)." >&2
  fi
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "az CLI not found." >&2
  print_cli_install_help
  exit 1
fi

# Infer owner/repo from git remote if not provided
if [[ -z "$OWNER" || -z "$REPO" ]]; then
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    remote=$(git remote get-url origin 2>/dev/null || true)
    if [[ -n "$remote" ]]; then
      # Supports https://github.com/OWNER/REPO(.git)
      # and git@github.com:OWNER/REPO(.git)
      remote=${remote%.git}
      if [[ "$remote" =~ github.com[:/]+([^/]+)/([^/]+)$ ]]; then
        OWNER=${OWNER:-"${BASH_REMATCH[1]}"}
        REPO=${REPO:-"${BASH_REMATCH[2]}"}
      fi
    fi
  fi
fi

if [[ -z "$OWNER" || -z "$REPO" ]]; then
  echo "Cannot determine --owner/--repo. Provide them explicitly." >&2
  exit 1
fi

if [[ -z "$GITHUB_REPO" ]]; then
  GITHUB_REPO="${OWNER}/${REPO}"
fi

if [[ -z "$SUBSCRIPTION_ID" ]]; then
  if ! SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null); then
    echo "ERROR: Azure CLI is not logged in for the current user." >&2
    echo "Run: az login" >&2
    echo "Tip: do NOT use sudo for this script; sudo will lose your az login context." >&2
    exit 1
  fi
fi
if [[ -z "$TENANT_ID" ]]; then
  if ! TENANT_ID=$(az account show --query tenantId -o tsv 2>/dev/null); then
    echo "ERROR: Azure CLI is not logged in for the current user." >&2
    echo "Run: az login" >&2
    echo "Tip: do NOT use sudo for this script; sudo will lose your az login context." >&2
    exit 1
  fi
fi

# Scope: prefer resource group if provided, else subscription
if [[ -n "$RESOURCE_GROUP" ]]; then
  SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"
else
  SCOPE="/subscriptions/${SUBSCRIPTION_ID}"
fi

echo "== GitHub =="
echo "repo: ${OWNER}/${REPO}"
echo "branch: ${BRANCH}"
echo "configure-github: ${CONFIGURE_GITHUB}"

echo "== Azure =="
echo "subscription: ${SUBSCRIPTION_ID}"
echo "tenant: ${TENANT_ID}"
echo "scope: ${SCOPE}"
echo "enable-swa: ${ENABLE_SWA}"
echo

# Create or reuse app registration
APP_ID=$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv || true)
if [[ -z "$APP_ID" ]]; then
  echo "Creating Entra app registration: ${APP_NAME}"
  APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
else
  echo "Reusing Entra app registration: ${APP_NAME} (${APP_ID})"
fi

# Ensure service principal exists
SP_OBJ_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query '[0].id' -o tsv || true)
if [[ -z "$SP_OBJ_ID" ]]; then
  echo "Creating service principal for appId ${APP_ID}"
  SP_OBJ_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
else
  echo "Reusing service principal (${SP_OBJ_ID})"
fi

# Federated credential (branch-scoped)
FIC_NAME="github-${OWNER}-${REPO}-${BRANCH}"
SUBJECT="repo:${OWNER}/${REPO}:ref:refs/heads/${BRANCH}"
PARAMS=$(cat <<JSON
{
  "name": "${FIC_NAME}",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "${SUBJECT}",
  "description": "GitHub Actions OIDC for ${OWNER}/${REPO} (${BRANCH})",
  "audiences": ["api://AzureADTokenExchange"]
}
JSON
)

EXISTING=$(az ad app federated-credential list --id "$APP_ID" --query "[?name=='${FIC_NAME}'].name" -o tsv || true)
if [[ -n "$EXISTING" ]]; then
  echo "Federated credential exists; replacing: ${FIC_NAME}"
  az ad app federated-credential delete --id "$APP_ID" --federated-credential-id "$FIC_NAME"
fi

echo "Creating federated credential: ${FIC_NAME}"
az ad app federated-credential create --id "$APP_ID" --parameters "$PARAMS" -o none

# RBAC
HAS_ROLE=$(az role assignment list --assignee "$APP_ID" --scope "$SCOPE" --query "[?roleDefinitionName=='${ROLE_NAME}'] | length(@)" -o tsv || echo 0)
if [[ "$HAS_ROLE" == "0" ]]; then
  echo "Creating role assignment: '${ROLE_NAME}' on ${SCOPE}"
  az role assignment create --assignee "$APP_ID" --role "$ROLE_NAME" --scope "$SCOPE" -o none
else
  echo "Role assignment already exists: '${ROLE_NAME}' on ${SCOPE}"
fi

if [[ "$ENABLE_SWA" == "true" ]]; then
  if [[ -n "$SWA_ROLE_OVERRIDE" ]]; then
    SWA_ROLE_NAME="$SWA_ROLE_OVERRIDE"
  else
    SWA_ROLE_NAME=""
    for candidate in "Website Contributor" "Static Web App Contributor" "Static Web Apps Contributor" "Contributor"; do
      found=$(az role definition list --name "$candidate" --query "[].name" -o tsv 2>/dev/null | head -n 1 || true)
      if [[ "$found" == "$candidate" ]]; then
        SWA_ROLE_NAME="$candidate"
        break
      fi
    done
    if [[ -z "$SWA_ROLE_NAME" ]]; then
      SWA_ROLE_NAME="Contributor"
    fi
  fi

  echo "SWA role: ${SWA_ROLE_NAME}"
  HAS_SWA_ROLE=$(az role assignment list --assignee "$APP_ID" --scope "$SCOPE" --query "[?roleDefinitionName=='${SWA_ROLE_NAME}'] | length(@)" -o tsv || echo 0)
  if [[ "$HAS_SWA_ROLE" == "0" ]]; then
    echo "Creating role assignment: '${SWA_ROLE_NAME}' on ${SCOPE}"
    az role assignment create --assignee "$APP_ID" --role "$SWA_ROLE_NAME" --scope "$SCOPE" -o none
  else
    echo "Role assignment already exists: '${SWA_ROLE_NAME}' on ${SCOPE}"
  fi
fi

if [[ "$CONFIGURE_GITHUB" == "true" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo
    echo "ERROR: GitHub CLI (gh) not found. Install it or run without --configure-github." >&2
    print_cli_install_help
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo
    echo "ERROR: gh is not authenticated. Run: gh auth login" >&2
    exit 1
  fi

  echo
  echo "== Auto-configuring GitHub Actions Variables via gh =="
  echo "repo: ${GITHUB_REPO}"

  gh variable set -R "$GITHUB_REPO" AZURE_CLIENT_ID -b "$APP_ID" >/dev/null
  gh variable set -R "$GITHUB_REPO" AZURE_TENANT_ID -b "$TENANT_ID" >/dev/null
  gh variable set -R "$GITHUB_REPO" AZURE_SUBSCRIPTION_ID -b "$SUBSCRIPTION_ID" >/dev/null

  if [[ -n "$RESOURCE_GROUP" ]]; then
    gh variable set -R "$GITHUB_REPO" AZURE_RESOURCE_GROUP -b "$RESOURCE_GROUP" >/dev/null
  fi

  if [[ -n "$AI_PROJECT_ENDPOINT" ]]; then
    gh variable set -R "$GITHUB_REPO" AZURE_AI_PROJECT_ENDPOINT -b "$AI_PROJECT_ENDPOINT" >/dev/null
  fi
  if [[ -n "$AI_MODEL_DEPLOYMENT_NAME" ]]; then
    gh variable set -R "$GITHUB_REPO" AZURE_AI_MODEL_DEPLOYMENT_NAME -b "$AI_MODEL_DEPLOYMENT_NAME" >/dev/null
  fi

  echo
  echo "== Done: GitHub Actions Variables written =="
  echo "repo: ${GITHUB_REPO}"
  echo "AZURE_CLIENT_ID=${APP_ID}"
  echo "AZURE_TENANT_ID=${TENANT_ID}"
  echo "AZURE_SUBSCRIPTION_ID=${SUBSCRIPTION_ID}"
  if [[ -n "$RESOURCE_GROUP" ]]; then
    echo "AZURE_RESOURCE_GROUP=${RESOURCE_GROUP}"
  else
    echo "AZURE_RESOURCE_GROUP=(NOT set; pass --resource-group or set it manually)"
  fi
  if [[ -n "$AI_PROJECT_ENDPOINT" ]]; then
    echo "AZURE_AI_PROJECT_ENDPOINT=(set)"
  else
    echo "AZURE_AI_PROJECT_ENDPOINT=(NOT set; pass --ai-project-endpoint or set it manually)"
  fi
  if [[ -n "$AI_MODEL_DEPLOYMENT_NAME" ]]; then
    echo "AZURE_AI_MODEL_DEPLOYMENT_NAME=${AI_MODEL_DEPLOYMENT_NAME}"
  else
    echo "AZURE_AI_MODEL_DEPLOYMENT_NAME=(not set; workflow default is gpt-5-mini)"
  fi
else
  print_manual_vars_instructions
fi
