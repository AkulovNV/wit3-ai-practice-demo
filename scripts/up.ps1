# Поднять стенд (Windows, PowerShell 5.1+). Повторный запуск безопасен.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\up.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Models = "qwen2.5-coder:7b", "qwen2.5:7b", "nomic-embed-text"
$Ports = 3000, 3001, 3002, 4000, 8000, 8080, 9090, 15432

function Ok($m)   { Write-Host "[ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!]  $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[x]  $m" -ForegroundColor Red; exit 1 }
function Run { & $args[0] $args[1..($args.Count - 1)]; if ($LASTEXITCODE -ne 0) { Die "команда упала: $args" } }
function Test-Url($u) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $u | Out-Null; $true } catch { $false } }

# --- preflight ---
docker info *> $null; if ($LASTEXITCODE -ne 0) { Die "Docker не запущен. Запустите Docker Desktop." }
docker compose version *> $null; if ($LASTEXITCODE -ne 0) { Die "Нет docker compose v2. Обновите Docker Desktop." }
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Ok "создан .env из .env.example" }
$Profiles = ((Select-String -Path .env -Pattern '^COMPOSE_PROFILES=(.*)').Matches.Groups[1].Value) -split ','

$memGb = [math]::Floor([double](docker info --format '{{.MemTotal}}') / 1GB)
if ($memGb -ge 6) { Ok "памяти у Docker: $memGb GB" }
else { Warn "памяти у Docker $memGb GB, нужно >= 6 GB: Docker Desktop -> Settings -> Resources (или memory в %UserProfile%\.wslconfig)" }

$freeGb = [math]::Floor((Get-PSDrive (Get-Location).Drive.Name).Free / 1GB)
if ($freeGb -ge 20) { Ok "свободно на диске: $freeGb GB" }
else { Warn "свободно $freeGb GB, нужно ~20 GB (модели ~10 GB + образы ~10 GB)" }

if (-not (docker compose ps -q)) {
  foreach ($p in $Ports) {
    $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { Die "порт $p занят: $((Get-Process -Id $c.OwningProcess).ProcessName). Освободите его или поменяйте порт в docker-compose.yml" }
  }
  Ok "порты свободны"
}

$InContainer = $Profiles -contains "ollama"
if (-not $InContainer) {
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Die "Ollama не установлена: winget install Ollama.Ollama (или https://ollama.com/download)" }
  if (-not (Test-Url "http://localhost:11434/api/version")) { Die "Ollama не запущена: откройте приложение Ollama из меню Пуск" }
  Ok "Ollama на хосте"
}

# --- стенд ---
Run docker compose up -d --build

foreach ($m in $Models) {
  if ($InContainer) { Run docker compose exec -T ollama ollama pull $m } else { Run ollama pull $m }
}
Ok "модели скачаны"

if ($Profiles -contains "ci") {
  while (-not (Test-Url "http://localhost:3002/api/healthz")) { Start-Sleep 2 }
  docker compose exec -T -u git gitea gitea admin user create --admin --username wit --password wit3-password `
    --email wit@wit3.local --must-change-password=false *> $null  # «уже существует» — нормально
}

Run docker compose run --rm --build tools python setup.py

Write-Host @"

Стенд поднят:
  Open WebUI   http://localhost:8080
  LiteLLM      http://localhost:4000/ui     (admin / sk-master-wit3-local)
  Langfuse     http://localhost:3001        (admin@wit3.local / wit3-admin)
  Grafana      http://localhost:3000        (дашборд «Demo API (shop)»)
  Gitea        http://localhost:3002        (wit / wit3-password)
  Prometheus   http://localhost:9090
  demo-api     http://localhost:8000/docs
"@
