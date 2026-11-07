"""Первичная настройка стенда (идемпотентно): ключи в LiteLLM, репозиторий + PR в Gitea."""
import os
import shutil
import subprocess
import sys
import time

import httpx

E = os.environ
LITELLM = E["LITELLM_BASE_URL"]
GITEA = E["GITEA_URL"]
GITEA_USER, GITEA_PASS = "wit", "wit3-password"


def wait(url, name, tries=90):
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2)
    print(f"✗ {name} не отвечает: {url}")
    return False


def litellm_keys():
    if not wait(f"{LITELLM}/health/liveliness", "LiteLLM"):
        sys.exit(1)
    h = {"Authorization": f"Bearer {E['LITELLM_MASTER_KEY']}"}
    keys = {
        # ключ менти: Open WebUI, IDE, агент, CI
        E["LITELLM_USER_KEY"]: {"key_alias": "mentee", "max_budget": 5, "rpm_limit": 60},
        # ключ для демо бюджета и rate limit: кончается через пару запросов
        "sk-limited-wit3-demo": {"key_alias": "limited-demo", "max_budget": 0.002, "rpm_limit": 2},
    }
    for key, params in keys.items():
        if httpx.get(f"{LITELLM}/key/info", params={"key": key}, headers=h).status_code == 200:
            print(f"✓ ключ {params['key_alias']} уже есть")
            continue
        r = httpx.post(f"{LITELLM}/key/generate", headers=h, json={"key": key, **params})
        if r.is_error:
            sys.exit(f"✗ ключ {params['key_alias']}: {r.text}")
        print(f"✓ создан ключ {params['key_alias']}")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def gitea_repo():
    if not wait(f"{GITEA}/api/healthz", "Gitea", tries=5):
        print("  Gitea не запущена (профиль ci выключен?) — пропускаю")
        return
    api = httpx.Client(base_url=f"{GITEA}/api/v1", auth=(GITEA_USER, GITEA_PASS))
    if api.get("/user").status_code == 401:
        print("✗ нет пользователя wit в Gitea — его создаёт scripts/up.*")
        sys.exit(1)
    if api.get(f"/repos/{GITEA_USER}/shop").status_code == 200:
        print("✓ репозиторий wit/shop уже есть")
        return
    api.post("/user/repos", json={"name": "shop", "default_branch": "main"}).raise_for_status()
    api.put(f"/repos/{GITEA_USER}/shop/actions/secrets/LITELLM_KEY", json={"data": E["LITELLM_USER_KEY"]}).raise_for_status()

    src = "/tmp/shop"
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree("/workspace/demo-api", src, ignore=shutil.ignore_patterns("__pycache__", "pr"))
    remote = f"http://{GITEA_USER}:{GITEA_PASS}@gitea:3000/{GITEA_USER}/shop.git"
    git("init", "-b", "main", cwd=src)
    git("-c", "user.name=wit", "-c", "user.email=wit@wit3.local", "add", ".", cwd=src)
    git("-c", "user.name=wit", "-c", "user.email=wit@wit3.local", "commit", "-m", "shop service", cwd=src)
    git("push", remote, "main", cwd=src)
    # PR с новой фичей для AI-ревью (в ней тоже есть баги)
    git("checkout", "-b", "feature/coupons", cwd=src)
    shutil.copy("/workspace/demo-api/pr/coupons.py", f"{src}/app/coupons.py")
    git("add", ".", cwd=src)
    git("-c", "user.name=wit", "-c", "user.email=wit@wit3.local", "commit", "-m", "coupons endpoint", cwd=src)
    git("push", remote, "feature/coupons", cwd=src)
    for _ in range(15):  # Gitea индексирует ветку после push асинхронно
        r = api.post(f"/repos/{GITEA_USER}/shop/pulls",
                     json={"title": "Coupons endpoint", "head": "feature/coupons", "base": "main"})
        if r.status_code != 404:
            break
        time.sleep(1)
    r.raise_for_status()
    print("✓ репозиторий wit/shop и PR #1 созданы — AI-ревью запустится в Gitea Actions")


def smoke():
    """Один запрос ключом менти: клиент → LiteLLM → Ollama → трейс в Langfuse."""
    r = httpx.post(f"{LITELLM}/v1/chat/completions", timeout=300,
                   headers={"Authorization": f"Bearer {E['LITELLM_USER_KEY']}"},
                   json={"model": "local-coder", "messages": [{"role": "user", "content": "Ответь одним словом: работает?"}]})
    if r.is_error:
        sys.exit(f"✗ запрос к модели через LiteLLM: {r.text}")
    print("✓ модель отвечает через LiteLLM:", r.json()["choices"][0]["message"]["content"].strip())


if __name__ == "__main__":
    litellm_keys()
    gitea_repo()
    smoke()
