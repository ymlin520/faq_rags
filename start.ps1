$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.\.venv\Scripts\python.exe')) { throw '尚未安裝，請先執行 .\setup.ps1' }
if (-not (Test-Path '.\admin-token.txt')) { throw '缺少本機密碼，請先執行 .\setup.ps1' }
$env:FAQ_ADMIN_TOKEN = (Get-Content -Raw '.\admin-token.txt').Trim()
if (Test-Path '.\default-email.txt') { $env:FAQ_DEFAULT_EMAIL = (Get-Content -Raw '.\default-email.txt').Trim() }
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
try { Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null }
catch {
  if (-not (Test-Path $ollama)) { throw '找不到 Ollama，請先安裝。' }
  Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
  Start-Sleep -Seconds 4
}
if (-not (Test-Path '.\data\qdrant-local\collection\school_faq\storage.sqlite')) {
  & '.\.venv\Scripts\python.exe' '.\scripts\import_faq.py'
  if ($LASTEXITCODE -ne 0) { throw 'FAQ 首次匯入失敗。' }
}
$existing = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if (-not $existing) {
  $proc = Start-Process '.\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','backend.main:app','--host','0.0.0.0','--port','8001' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput '.\server.out.log' -RedirectStandardError '.\server.err.log' -PassThru
  Set-Content '.\backend.pid' $proc.Id -Encoding ascii
}
$ready = $false
foreach ($attempt in 1..60) {
  try { $health = Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 10; $ready = $true; break }
  catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { throw '服務未能啟動，請查看 server.err.log。' }
Write-Host "服務已啟動：http://127.0.0.1:8001（FAQ $($health.points) 筆）"
Start-Process 'http://127.0.0.1:8001'
