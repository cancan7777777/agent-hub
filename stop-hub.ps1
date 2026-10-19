# 停止 agent-hub 服务
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
# 只停本项目的实例，别误杀其他项目里恰好叫 server.py 的进程
$pat = [regex]::Escape((Join-Path $Root "core\server.py"))
$found = $false
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -match $pat } |
  ForEach-Object { $found = $true; Write-Host "stopped PID $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
if (-not $found) { Write-Host "没有正在运行的实例" }
