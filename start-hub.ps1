# agent-hub 启动脚本：后台运行控制台，可选自动打开浏览器
# 用法：  .\start-hub.ps1            启动并打开浏览器
#         .\start-hub.ps1 -Port 9000 换端口
#         .\start-hub.ps1 -NoBrowser 后台启动不开浏览器
param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 停掉已在运行的实例
# 只停本项目的实例，别误杀其他项目里恰好叫 server.py 的进程
$pat = [regex]::Escape((Join-Path $Root "core\server.py"))
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -match $pat } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1

$env:HUB_NO_BROWSER = if ($NoBrowser) { "1" } else { "" }
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Path (Join-Path $Root "logs") -Force | Out-Null
# 用绝对路径启动，命令行里就带得上项目位置，stop/start 的匹配才不会认错进程
Start-Process -FilePath "python" -ArgumentList (Join-Path $Root "core\server.py"), "$Port" `
  -WorkingDirectory (Join-Path $Root "core") -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $Root "logs\hub.out.log") `
  -RedirectStandardError  (Join-Path $Root "logs\hub.err.log")
Start-Sleep -Seconds 2
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
Write-Host "agent-hub  ->  http://127.0.0.1:$Port/"
