param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$userDeepSeekKey = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
if (-not $env:DEEPSEEK_API_KEY -and $userDeepSeekKey) { $env:DEEPSEEK_API_KEY = $userDeepSeekKey }
$userArtClawKey = [Environment]::GetEnvironmentVariable("ARTCLAW_API_KEY_ACCOUNT_A", "User")
if (-not $env:ARTCLAW_API_KEY_ACCOUNT_A -and $userArtClawKey) { $env:ARTCLAW_API_KEY_ACCOUNT_A = $userArtClawKey }
$userImageApiKey = [Environment]::GetEnvironmentVariable("IMAGE_API_KEY", "User")
if (-not $env:IMAGE_API_KEY -and $userImageApiKey) { $env:IMAGE_API_KEY = $userImageApiKey }
$userImageApiBaseUrl = [Environment]::GetEnvironmentVariable("IMAGE_API_BASE_URL", "User")
if (-not $env:IMAGE_API_BASE_URL -and $userImageApiBaseUrl) { $env:IMAGE_API_BASE_URL = $userImageApiBaseUrl }
$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "未找到 Docker，请先安装 Docker Desktop" }
if ($Build) { docker compose -f $composeFile up --build } else { docker compose -f $composeFile up }
