# 停止 agent-hub 服务
$ErrorActionPreference = "SilentlyContinue"
$found = $false
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -match "server\.py" } |
  ForEach-Object { $found = $true; Write-Host "stopped PID $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
if (-not $found) { Write-Host "没有正在运行的实例" }
