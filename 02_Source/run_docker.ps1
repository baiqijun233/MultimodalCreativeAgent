param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$userDeepSeekKey = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
if (-not $env:DEEPSEEK_API_KEY -and $userDeepSeekKey) { $env:DEEPSEEK_API_KEY = $userDeepSeekKey }
$userArtClawKey = [Environment]::GetEnvironmentVariable("ARTCLAW_API_KEY_ACCOUNT_A", "User")
if (-not $env:ARTCLAW_API_KEY_ACCOUNT_A -and $userArtClawKey) { $env:ARTCLAW_API_KEY_ACCOUNT_A = $userArtClawKey }
$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "未找到 Docker，请先安装 Docker Desktop" }
if ($Build) { docker compose -f $composeFile up --build } else { docker compose -f $composeFile up }
