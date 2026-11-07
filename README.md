# WIT3 — AI-стенд

Локальная AI-экосистема вокруг небольшого сервиса: модели, gateway, чат, агент с MCP, AI-ревью в CI, observability.
Всё работает на локальных моделях, без облака и без GPU.

```
 Open WebUI ─┐
 IDE (Continue/Aider) ─┤                    ┌─► Ollama (на хосте): qwen2.5-coder:7b, qwen2.5:7b, nomic-embed-text
 агент + MCP ─┼─► LiteLLM (ключи, бюджеты, ─┤
 Gitea CI ───┘    rate limit, логи)         └─► облачная модель (опционально, алиас cloud)
                        │
                        └─► Langfuse (трейсы, токены, стоимость)

 demo-api (FastAPI + Postgres, с багами) ─► Prometheus + Loki ─► Grafana
```

Правило стенда: **ни один клиент не ходит в модель напрямую, только через LiteLLM** (`http://localhost:4000`).
Клиенты знают алиасы моделей, а не провайдеров:

| Алиас | Модель | Для чего |
|---|---|---|
| `local-coder` | qwen2.5-coder:7b | код, ревью, чат |
| `local-general` | qwen2.5:7b | агенты (нативный tool calling) |
| `local-embed` | nomic-embed-text | эмбеддинги для RAG |
| `cloud` | Claude через API | опционально, нужен `ANTHROPIC_API_KEY` в `.env` |

## Требования

- 16 GB RAM, ~25 GB свободного диска, GPU не нужен
- **Docker Desktop** (macOS / Windows), в настройках Resources → Memory **не меньше 6 GB**
- **Ollama**, установленная нативно (не в Docker): на Mac так работает Metal-ускорение, и это экономит 7 GB на образе
- Windows: Docker Desktop на WSL2 (по умолчанию), PowerShell 5.1+

Сколько занимает в памяти (замерено): контейнеры ~4.5 GB, Ollama с загруженной 7B-моделью ~5.5 GB.

## Установка

### macOS

```bash
brew install ollama && brew services start ollama   # или приложение с https://ollama.com/download
git clone <url-репозитория> wit3 && cd wit3
./scripts/up.sh
```

### Windows

```powershell
winget install Ollama.Ollama          # затем запустите Ollama из меню Пуск
git clone <url-репозитория> wit3; cd wit3
powershell -ExecutionPolicy Bypass -File scripts\up.ps1
```

Скрипт `up` проверяет Docker, память, диск, порты и Ollama, создаёт `.env`, поднимает контейнеры, скачивает модели (~10 GB,
первый раз долго), создаёт ключи в LiteLLM и репозиторий с PR в Gitea, а в конце делает тестовый запрос к модели.
Запускать повторно безопасно.

Первый запуск: 15–40 минут в зависимости от интернета. Дальше около минуты.

## Адреса и доступы

| Что | Адрес | Логин |
|---|---|---|
| Open WebUI (чат) | http://localhost:8080 | без логина |
| LiteLLM (gateway) | http://localhost:4000, UI: `/ui` | `admin` / `sk-master-wit3-local` |
| Langfuse (трейсы LLM) | http://localhost:3001 | `admin@wit3.local` / `wit3-admin` |
| Grafana | http://localhost:3000 | без логина; дашборд «Demo API (shop)» |
| Gitea (git + CI) | http://localhost:3002 | `wit` / `wit3-password` |
| Prometheus | http://localhost:9090 | — |
| demo-api (Swagger) | http://localhost:8000/docs | — |
| Postgres | `localhost:15432` | `shop`/`shop` (владелец), `agent_ro`/`agent_ro` (только чтение) |

Ключи LiteLLM:
- `sk-mentee-wit3-local` — ваш рабочий ключ (бюджет $5 условных, 60 запросов/мин): им ходят Open WebUI, IDE, агент, CI.
- `sk-limited-wit3-demo` — ключ для демонстрации лимитов (2 запроса/мин, бюджет $0.002).

Цены у локальных моделей условные (`config/litellm.yaml`), чтобы бюджеты и учёт стоимости работали так же, как с облаком.

## ДЗ №0 (до 21.11)

1. Установить Docker Desktop и Ollama, клонировать репо, запустить `scripts/up.sh` (или `up.ps1`) и дождаться «Стенд поднят».
2. Открыть Open WebUI → выбрать `local-coder` → задать вопрос.
3. Открыть Langfuse → Tracing: найти свой запрос; посмотреть токены, латентность, стоимость.
4. Открыть Grafana → дашборд «Demo API (shop)»: RPS, ошибки, латентность и логи демо-сервиса.
5. Записать, что было непонятно или сломалось. Это тоже результат.

## Что можно делать на стенде

Все команды запускаются из корня репозитория. На Windows вместо `curl` используйте `curl.exe`.

**1. Запрос через gateway, бюджет и rate limit**
```bash
curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-mentee-wit3-local" \
  -H "Content-Type: application/json" -d '{"model":"local-coder","messages":[{"role":"user","content":"Привет"}]}'
# тот же запрос с ключом sk-limited-wit3-demo: третий за минуту → 429, а через ~6 запросов кончится бюджет
```

**2. Агент с одним тулом** (HTTP GET к demo-api):
```bash
docker compose run --rm tools python agent.py "Какие отзывы оставили на товар 1?"
```

**3. Агент через MCP** (серверы: `git`, `postgres`, `prometheus`, `loki`):
```bash
docker compose run --rm tools python agent.py --mcp postgres,prometheus "Сколько заказов в базе и какой RPS у demo-api?"
docker compose run --rm tools python agent.py --mcp git "Какой последний коммит?"
```
`postgres` и `loki` — самописные MCP-серверы на 30 строк (`tools/mcp_*.py`), образец для ДЗ занятия 2.

**4. AI-ревью PR в CI.** Gitea → `wit/shop` → Pull Requests → #1: в комментарии ревью от модели.
Workflow с чеклистом лежит в `demo-api/.gitea/workflows/ai-review.yml`.
Новый PR в `wit/shop` запускает ревью снова.

**Параметры агента**
```bash
docker compose run --rm tools python agent.py --help
#   --mcp git,postgres,prometheus,loki   какие MCP-серверы подключить (без флага — один HTTP-тул к demo-api)
#   --model local-general|local-coder|cloud
#   -e ALLOWED_TOOLS=postgres__list_tables,...   allowlist тулов
#   -e DATABASE_URI=postgresql://...             под какой ролью ходит postgres-MCP (по умолчанию agent_ro, только чтение)
```

Агент на 7B-модели ошибается: пишет кривой PromQL, может выдумать вывод. Это нормально и полезно для разбора.
Сравните с `--model cloud`, если подключён облачный ключ. Каждый запуск агента — один трейс в Langfuse.

## IDE-ассистент через gateway (ДЗ занятия 1)

OpenAI-совместимый endpoint: `http://localhost:4000/v1`, ключ `sk-mentee-wit3-local`, модель `local-coder`.

- **Continue** (VS Code / JetBrains), `~/.continue/config.yaml`:
  ```yaml
  name: wit3
  version: 0.0.1
  schema: v1
  models:
    - name: local-coder
      provider: openai
      model: local-coder
      apiBase: http://localhost:4000/v1
      apiKey: sk-mentee-wit3-local
  ```
- **Aider**:
  ```bash
  OPENAI_API_BASE=http://localhost:4000/v1 OPENAI_API_KEY=sk-mentee-wit3-local aider --model openai/local-coder
  ```

## Личный AI-workflow

Как работать с AI-ассистентом каждый день: [docs/ai-workflow.md](docs/ai-workflow.md) (ДЗ занятия 1).

## Управление

```bash
docker compose ps                 # что запущено
docker compose logs -f litellm    # логи сервиса
docker compose stop               # остановить (данные сохранятся)
docker compose down -v            # снести стенд вместе с данными; потом заново scripts/up.*
```

Слои включаются через `COMPOSE_PROFILES` в `.env`:
- `ci` — Gitea + runner (нужно с занятия 2). Если не хватает памяти, уберите и сэкономите ~150 MB.
- `ollama` — Ollama в контейнере вместо нативной. Используйте, только если нативная не ставится:
  медленнее, +7 GB образ. Тогда же поменяйте `OLLAMA_BASE_URL=http://ollama:11434`.

## Troubleshooting

| Симптом | Что делать |
|---|---|
| `порт XXXX занят` | Найти процесс (`lsof -i :3000` / `Get-NetTCPConnection -LocalPort 3000`) и остановить, либо поменять левую часть порта в `docker-compose.yml` |
| `памяти у Docker N GB` | Docker Desktop → Settings → Resources → Memory ≥ 6 GB. Windows/WSL2: `%UserProfile%\.wslconfig` → `[wsl2]` `memory=8GB`, затем `wsl --shutdown` |
| Ответ модели очень медленный | Первый запрос грузит модель в память (10–30 с). На CPU 7B выдаёт 3–10 токенов/с, это нормально. Закройте лишние приложения |
| LiteLLM: `Connection refused` к Ollama | Ollama не запущена: macOS `brew services start ollama`, Windows — приложение Ollama. Проверка: http://localhost:11434 |
| Windows: Ollama запущена, но из контейнера недоступна | Задайте переменную окружения `OLLAMA_HOST=0.0.0.0` для Ollama и перезапустите её; проверьте фаервол |
| `up.ps1 cannot be loaded ... execution policy` | Запускать через `powershell -ExecutionPolicy Bypass -File scripts\up.ps1` |
| Скрипты/конфиги с CRLF на Windows | Репо форсит LF (`.gitattributes`). Если клонировали до этого: `git rm --cached -r . && git reset --hard` |
| Нет трейсов в Langfuse | Подождать 10–30 с (асинхронная запись); `docker compose logs litellm \| grep -i langfuse` |
| В Grafana нет логов нового контейнера | Alloy находит контейнеры раз в минуту, подождите |
| Docker старый | Нужен Docker Desktop 4.30+ (compose v2). Проверка: `docker compose version` |
| Всё сломалось | `docker compose down -v` и заново `scripts/up.sh` / `up.ps1` |

## Структура

```
docker-compose.yml        весь стенд
.env.example              порты/ключи/профили (копируется в .env)
config/                   litellm, postgres init (схема + данные), prometheus, alloy, grafana, runner
demo-api/                 подопытный сервис (FastAPI + Postgres) с намеренными багами; пушится в Gitea как wit/shop
demo-api/.gitea/workflows AI-ревью PR
demo-api/pr/              фича для PR #1 (материал для AI-ревью)
tools/                    агент, MCP-серверы postgres/loki, setup, loadgen
scripts/up.sh, up.ps1     запуск для macOS / Windows
docs/ai-workflow.md       гайд по личному AI-workflow
```
