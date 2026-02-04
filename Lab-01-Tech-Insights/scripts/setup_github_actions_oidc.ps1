Param(
  [string]$AppName = "gcr-ai-tour-gha-oidc",
  [string]$Owner = "",
  [string]$Repo = "",
  [string]$Branch = "main",
  [string]$ResourceGroup = "",
  [string]$SubscriptionId = "",
  [string]$TenantId = "",
  [string]$Role = "Cognitive Services User",
  [switch]$EnableSwa,
  [string]$SwaRole = "",
  [switch]$ConfigureGitHub,
  [string]$GitHubRepo = "",
  [string]$AiProjectEndpoint = "",
  [string]$AiModelDeploymentName = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
  Write-Host $Message
}

function Require-Command([string]$Name, [string]$InstallUrl) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "Missing required CLI: $Name`nInstall: $InstallUrl"
  }
}

Require-Command -Name "az" -InstallUrl "https://learn.microsoft.com/cli/azure/install-azure-cli"
if ($ConfigureGitHub) {
  Require-Command -Name "gh" -InstallUrl "https://cli.github.com/"
}

# Infer owner/repo from git remote if not provided
if ([string]::IsNullOrWhiteSpace($Owner) -or [string]::IsNullOrWhiteSpace($Repo)) {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if ($git) {
    try {
      $remote = (git remote get-url origin 2>$null)
      if ($remote) {
        $remote = $remote.Trim()
        if ($remote.EndsWith(".git")) { $remote = $remote.Substring(0, $remote.Length - 4) }

        # https://github.com/OWNER/REPO or git@github.com:OWNER/REPO
        $m = [regex]::Match($remote, "github.com[:/]+([^/]+)/([^/]+)$")
        if ($m.Success) {
          if ([string]::IsNullOrWhiteSpace($Owner)) { $Owner = $m.Groups[1].Value }
          if ([string]::IsNullOrWhiteSpace($Repo)) { $Repo = $m.Groups[2].Value }
        }
      }
    } catch {
      # ignore
    }
  }
}

if ([string]::IsNullOrWhiteSpace($Owner) -or [string]::IsNullOrWhiteSpace($Repo)) {
  throw "Cannot determine -Owner/-Repo. Provide them explicitly, or run from a git clone with origin remote."
}

if ([string]::IsNullOrWhiteSpace($GitHubRepo)) {
  $GitHubRepo = "$Owner/$Repo"
}

if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
  $SubscriptionId = (az account show --query id -o tsv).Trim()
}
if ([string]::IsNullOrWhiteSpace($TenantId)) {
  $TenantId = (az account show --query tenantId -o tsv).Trim()
}

# Scope: prefer resource group if provided, else subscription
if (-not [string]::IsNullOrWhiteSpace($ResourceGroup)) {
  $scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
} else {
  $scope = "/subscriptions/$SubscriptionId"
}

Write-Info "== GitHub =="
Write-Info "repo: $Owner/$Repo"
Write-Info "branch: $Branch"
Write-Info "== Azure =="
Write-Info "subscription: $SubscriptionId"
Write-Info "tenant: $TenantId"
Write-Info "scope: $scope"
Write-Info "enable-swa: $EnableSwa"
Write-Info ""

# Create or reuse app registration
$appId = (az ad app list --display-name $AppName --query "[0].appId" -o tsv 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($appId)) {
  Write-Info "Creating Entra app registration: $AppName"
  $appId = (az ad app create --display-name $AppName --query appId -o tsv).Trim()
} else {
  Write-Info "Reusing Entra app registration: $AppName ($appId)"
}

# Ensure service principal exists
$spObjId = (az ad sp list --filter "appId eq '$appId'" --query "[0].id" -o tsv 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($spObjId)) {
  Write-Info "Creating service principal for appId $appId"
  $spObjId = (az ad sp create --id $appId --query id -o tsv).Trim()
} else {
  Write-Info "Reusing service principal ($spObjId)"
}

# Federated credential (branch-scoped)
$ficName = "github-$Owner-$Repo-$Branch"
$subject = "repo:$Owner/$Repo:ref:refs/heads/$Branch"

# Replace if exists
$existing = (az ad app federated-credential list --id $appId --query "[?name=='$ficName'].name" -o tsv 2>$null).Trim()
if (-not [string]::IsNullOrWhiteSpace($existing)) {
  Write-Info "Federated credential exists; replacing: $ficName"
  az ad app federated-credential delete --id $appId --federated-credential-id $ficName | Out-Null
}

$tempPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "fic-$ficName.json")
$payload = @{
  name        = $ficName
  issuer      = "https://token.actions.githubusercontent.com"
  subject     = $subject
  description = "GitHub Actions OIDC for $Owner/$Repo ($Branch)"
  audiences   = @("api://AzureADTokenExchange")
} | ConvertTo-Json -Depth 10

Set-Content -Path $tempPath -Value $payload -Encoding UTF8
try {
  Write-Info "Creating federated credential: $ficName"
  az ad app federated-credential create --id $appId --parameters "@$tempPath" -o none
} finally {
  Remove-Item -Force -ErrorAction SilentlyContinue $tempPath
}

# RBAC
$hasRole = (az role assignment list --assignee $appId --scope $scope --query "[?roleDefinitionName=='$Role'] | length(@)" -o tsv 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($hasRole)) { $hasRole = "0" }
if ($hasRole -eq "0") {
  Write-Info "Creating role assignment: '$Role' on $scope"
  az role assignment create --assignee $appId --role $Role --scope $scope -o none
} else {
  Write-Info "Role assignment already exists: '$Role' on $scope"
}

if ($EnableSwa) {
  if (-not [string]::IsNullOrWhiteSpace($SwaRole)) {
    $swaRole = $SwaRole
  } else {
    $swaRole = $null
    $candidates = @("Website Contributor", "Static Web App Contributor", "Static Web Apps Contributor", "Contributor")
    foreach ($candidate in $candidates) {
      try {
        $found = (az role definition list --name $candidate --query "[].name" -o tsv 2>$null).Trim()
      } catch {
        $found = ""
      }
      if ($found -eq $candidate) {
        $swaRole = $candidate
        break
      }
    }
    if ([string]::IsNullOrWhiteSpace($swaRole)) {
      $swaRole = "Contributor"
    }
  }

  Write-Info "SWA role: $swaRole"
  $hasSwaRole = (az role assignment list --assignee $appId --scope $scope --query "[?roleDefinitionName=='$swaRole'] | length(@)" -o tsv 2>$null).Trim()
  if ([string]::IsNullOrWhiteSpace($hasSwaRole)) { $hasSwaRole = "0" }
  if ($hasSwaRole -eq "0") {
    Write-Info "Creating role assignment: '$swaRole' on $scope"
    az role assignment create --assignee $appId --role $swaRole --scope $scope -o none
  } else {
    Write-Info "Role assignment already exists: '$swaRole' on $scope"
  }
}

Write-Info ""
if ($ConfigureGitHub) {
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) not found. Install it or run without -ConfigureGitHub."
  }

  # Ensure authenticated
  gh auth status | Out-Null

  Write-Info ""
  Write-Info "== Auto-configuring GitHub Actions Variables via gh =="
  Write-Info "repo: $GitHubRepo"

  gh variable set -R $GitHubRepo AZURE_CLIENT_ID -b $appId | Out-Null
  gh variable set -R $GitHubRepo AZURE_TENANT_ID -b $TenantId | Out-Null
  gh variable set -R $GitHubRepo AZURE_SUBSCRIPTION_ID -b $SubscriptionId | Out-Null

  if (-not [string]::IsNullOrWhiteSpace($ResourceGroup)) {
    gh variable set -R $GitHubRepo AZURE_RESOURCE_GROUP -b $ResourceGroup | Out-Null
  }

  if (-not [string]::IsNullOrWhiteSpace($AiProjectEndpoint)) {
    gh variable set -R $GitHubRepo AZURE_AI_PROJECT_ENDPOINT -b $AiProjectEndpoint | Out-Null
  }
  if (-not [string]::IsNullOrWhiteSpace($AiModelDeploymentName)) {
    gh variable set -R $GitHubRepo AZURE_AI_MODEL_DEPLOYMENT_NAME -b $AiModelDeploymentName | Out-Null
  }

  Write-Info ""
  Write-Info "== Done: GitHub Actions Variables written =="
  Write-Info "repo: $GitHubRepo"
  Write-Info "AZURE_CLIENT_ID=$appId"
  Write-Info "AZURE_TENANT_ID=$TenantId"
  Write-Info "AZURE_SUBSCRIPTION_ID=$SubscriptionId"
  if (-not [string]::IsNullOrWhiteSpace($ResourceGroup)) {
    Write-Info "AZURE_RESOURCE_GROUP=$ResourceGroup"
  } else {
    Write-Info "AZURE_RESOURCE_GROUP=(NOT set; pass -ResourceGroup or set it manually)"
  }
  if (-not [string]::IsNullOrWhiteSpace($AiProjectEndpoint)) {
    Write-Info "AZURE_AI_PROJECT_ENDPOINT=(set)"
  } else {
    Write-Info "AZURE_AI_PROJECT_ENDPOINT=(NOT set; pass -AiProjectEndpoint or set it manually)"
  }
  if (-not [string]::IsNullOrWhiteSpace($AiModelDeploymentName)) {
    Write-Info "AZURE_AI_MODEL_DEPLOYMENT_NAME=$AiModelDeploymentName"
  } else {
    Write-Info "AZURE_AI_MODEL_DEPLOYMENT_NAME=(not set; workflow default is gpt-5-mini)"
  }
} else {
  Write-Info "== Next step: set GitHub Actions Repository Variables (recommended for labs) =="
  Write-Info "In your GitHub repo: Settings → Secrets and variables → Actions → Variables"
  Write-Info ""
  Write-Info "Create these Variables:"
  Write-Info "  AZURE_CLIENT_ID=$appId"
  Write-Info "  AZURE_TENANT_ID=$TenantId"
  Write-Info "  AZURE_SUBSCRIPTION_ID=$SubscriptionId"
  Write-Info ""
  Write-Info "Also set (per-student):"
  Write-Info "  AZURE_AI_PROJECT_ENDPOINT=<your-foundry-project-endpoint>"
  Write-Info "  AZURE_AI_MODEL_DEPLOYMENT_NAME=<your-model-deployment>"
  Write-Info ""
  Write-Info "Tip: re-run with -ConfigureGitHub to auto-write Variables via gh."
}
