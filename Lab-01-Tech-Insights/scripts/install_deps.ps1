Param(
  [string]$VenvDir = "",
  [switch]$PythonOnly,
  [switch]$NoAzureCli,
  [switch]$NoGitHubCli
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($VenvDir)) {
  $VenvDir = Join-Path $RootDir ".venv"
}

function Write-Info([string]$Message) {
  Write-Host $Message
}

function Command-Exists([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Require-WingetOrExplain([string]$ToolName, [string]$InstallUrl) {
  Write-Warning "Missing required CLI: $ToolName"
  Write-Host "Install: $InstallUrl"
  if (-not (Command-Exists "winget")) {
    Write-Host "winget not found; install manually or use Windows Store/App Installer." 
    return $false
  }
  return $true
}

function Install-AzureCli {
  if ($PythonOnly -or $NoAzureCli) { return }
  if (Command-Exists "az") {
    Write-Info "Azure CLI already installed."
    return
  }
  if (-not (Require-WingetOrExplain -ToolName "az" -InstallUrl "https://learn.microsoft.com/cli/azure/install-azure-cli")) {
    return
  }
  Write-Info "Installing Azure CLI via winget..."
  winget install -e --id Microsoft.AzureCLI | Out-Null
}

function Install-GitHubCli {
  if ($PythonOnly -or $NoGitHubCli) { return }
  if (Command-Exists "gh") {
    Write-Info "GitHub CLI already installed."
    return
  }
  if (-not (Require-WingetOrExplain -ToolName "gh" -InstallUrl "https://cli.github.com/")) {
    return
  }
  Write-Info "Installing GitHub CLI via winget..."
  winget install -e --id GitHub.cli | Out-Null
}

function Setup-PythonEnv {
  if (-not (Command-Exists "python")) {
    throw "Python not found on PATH. Install Python 3.10+ first (https://www.python.org/downloads/) or via winget (e.g. 'winget install -e --id Python.Python.3.11')."
  }

  Write-Info "Setting up Python virtual environment..."
  if (-not (Test-Path $VenvDir)) {
    python -m venv $VenvDir
  }

  $activate = Join-Path $VenvDir "Scripts\Activate.ps1"
  if (-not (Test-Path $activate)) {
    throw "venv activate script not found: $activate"
  }

  & $activate

  python -m pip install --upgrade pip | Out-Null

  Write-Info "Installing Python dependencies..."
  $req = Join-Path $RootDir "requirements.txt"
  if (Test-Path $req) {
    python -m pip install -r $req
  } else {
    python -m pip install agent-framework azure-identity azure-ai-projects azure-core openai httpx python-dotenv pyyaml
  }

  Write-Info "Done. Virtual environment: $VenvDir"
  Write-Info "Activate with: $activate"
}

Install-AzureCli
Install-GitHubCli
Setup-PythonEnv
