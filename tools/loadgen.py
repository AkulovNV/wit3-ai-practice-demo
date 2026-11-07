"""Фоновая нагрузка на demo-api, чтобы в Grafana были живые метрики и логи."""
import random
import time

import httpx

paths = ["/products", "/products?page=2", "/products/search?name=key", "/products/1/reviews",
         "/users/1/orders", "/users/2/orders", "/users/2"]
with httpx.Client(base_url="http://demo-api:8000", timeout=10) as c:
    while True:
        try:
            c.get(random.choice(paths))
        except httpx.HTTPError as e:
            print("loadgen:", e, flush=True)
            time.sleep(2)
        time.sleep(0.3)
