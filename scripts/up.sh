#!/usr/bin/env bash
# Поднять стенд (macOS / Linux). Повторный запуск безопасен.
set -euo pipefail
cd "$(dirname "$0")/.."

MODELS="qwen2.5-coder:7b qwen2.5:7b nomic-embed-text"
PORTS="3000 3001 3002 4000 8000 8080 9090 15432"

ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*"; exit 1; }

# --- preflight ---
docker info >/dev/null 2>&1 || die "Docker не запущен. Запустите Docker Desktop."
docker compose version >/dev/null 2>&1 || die "Нет docker compose v2. Обновите Docker Desktop."
[ -f .env ] || { cp .env.example .env; ok "создан .env из .env.example"; }
PROFILES=$(grep -E '^COMPOSE_PROFILES=' .env | cut -d= -f2 || true)

mem_gb=$(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 ))
[ "$mem_gb" -ge 6 ] && ok "памяти у Docker: ${mem_gb} GB" \
  || warn "памяти у Docker ${mem_gb} GB, нужно ≥ 6 GB: Docker Desktop → Settings → Resources → Memory"

free_gb=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
[ "$free_gb" -ge 20 ] && ok "свободно на диске: ${free_gb} GB" \
  || warn "свободно ${free_gb} GB, нужно ~20 GB (модели ~10 GB + образы ~10 GB)"

if [ -z "$(docker compose ps -q 2>/dev/null)" ]; then
  for p in $PORTS; do
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      die "порт $p занят: $(lsof -nP -iTCP:"$p" -sTCP:LISTEN | awk 'NR==2 {print $1}'). Освободите его или поменяйте порт в docker-compose.yml"
    fi
  done
  ok "порты свободны"
fi

if [[ ",$PROFILES," != *",ollama,"* ]]; then
  command -v ollama >/dev/null || die "Ollama не установлена: brew install ollama (или https://ollama.com/download), затем brew services start ollama"
  curl -sf localhost:11434/api/version >/dev/null || die "Ollama не запущена: brew services start ollama (или откройте приложение Ollama)"
  ok "Ollama $(ollama --version 2>/dev/null | awk '{print $NF}') на хосте"
fi

# --- стенд ---
docker compose up -d --build

for m in $MODELS; do
  if [[ ",$PROFILES," == *",ollama,"* ]]; then docker compose exec -T ollama ollama pull "$m"
  else ollama pull "$m"; fi
done
ok "модели скачаны"

if [[ ",$PROFILES," == *",ci,"* ]]; then
  until curl -sf localhost:3002/api/healthz >/dev/null; do sleep 2; done
  docker compose exec -T -u git gitea gitea admin user create --admin --username wit --password wit3-password \
    --email wit@wit3.local --must-change-password=false >/dev/null 2>&1 || true
fi

docker compose run --rm --build tools python setup.py

cat <<'EOF'

Стенд поднят:
  Open WebUI   http://localhost:8080
  LiteLLM      http://localhost:4000/ui     (admin / sk-master-wit3-local)
  Langfuse     http://localhost:3001        (admin@wit3.local / wit3-admin)
  Grafana      http://localhost:3000        (дашборд «Demo API (shop)»)
  Gitea        http://localhost:3002        (wit / wit3-password)
  Prometheus   http://localhost:9090
  demo-api     http://localhost:8000/docs
EOF
