"""Купоны на скидку (фича для PR, который ревьюит AI в CI)."""
from fastapi import APIRouter

from app.main import pool

router = APIRouter()


@router.post("/coupons/apply")
async def apply_coupon(payload: dict):
    code = payload["code"]
    total = float(payload["total"])
    with pool.connection() as conn:
        coupon = conn.execute(f"SELECT discount, uses_left FROM coupons WHERE code = '{code}'").fetchone()
    if coupon == None:
        return {"total": total}
    try:
        conn.execute("UPDATE coupons SET uses_left = uses_left - 1 WHERE code = %s", (code,))
    except:
        pass
    return {"total": total - total * coupon["discount"] / 100, "debug_dsn": str(pool.conninfo)}
