param(
    [int]$Port = 8001,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$userDeepSeekKey = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
if (-not $env:DEEPSEEK_API_KEY -and $userDeepSeekKey) { $env:DEEPSEEK_API_KEY = $userDeepSeekKey }
$userArtClawKey = [Environment]::GetEnvironmentVariable("ARTCLAW_API_KEY_ACCOUNT_A", "User")
if (-not $env:ARTCLAW_API_KEY_ACCOUNT_A -and $userArtClawKey) { $env:ARTCLAW_API_KEY_ACCOUNT_A = $userArtClawKey }
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "multimodal_creative_agent")).Path
$env:PYTHONPATH = $sourceRoot
if (-not $env:TASK_DATABASE_PATH) { $env:TASK_DATABASE_PATH = (Join-Path $PSScriptRoot "..\04_Data\runtime\tasks.db") }
if (-not $env:ASSET_ROOT) { $env:ASSET_ROOT = (Join-Path $PSScriptRoot "..\04_Data\runtime\assets") }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:TASK_DATABASE_PATH), $env:ASSET_ROOT | Out-Null
Write-Host "平台启动中: http://${HostAddress}:$Port"
Write-Host "DeepSeek: $(if ($env:DEEPSEEK_API_KEY) { '已配置' } else { '未配置，将使用离线模型' })"
Write-Host "ArtClaw: $(if ($env:ARTCLAW_API_KEY_ACCOUNT_A -or $env:ARTCLAW_API_KEY) { '已配置' } else { '未配置' })"
python -m uvicorn app:app --host $HostAddress --port $Port
