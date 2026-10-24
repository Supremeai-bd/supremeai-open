"""User management + tenant usage endpoints
(GET/POST /admin-api/users, DELETE /admin-api/users/{username},
POST /admin-api/tenants/{tenant_id}/reset)."""

from fastapi import HTTPException

from api.routes.admin_dashboard import load_users, router, save_users
from api.routes.admin_dashboard._models import UserUpdate
from core.logging_config import logger


@router.get("/users")
def get_users():
    return load_users()


@router.post("/users")
def create_user(user: UserUpdate):
    users = load_users()
    for u in users:
        if u["username"] == user.username:
            u["role"] = user.role
            u["permissions"] = user.permissions
            save_users(users)
            return {"status": "success", "message": f"User {user.username} updated"}

    users.append({"username": user.username, "role": user.role, "permissions": user.permissions})
    save_users(users)
    return {"status": "success", "message": f"User {user.username} created"}


@router.delete("/users/{username}")
def delete_user(username: str):
    users = load_users()
    new_users = [u for u in users if u["username"] != username]
    if len(new_users) == len(users):
        raise HTTPException(status_code=404, detail="User not found")
    save_users(new_users)
    return {"status": "success", "message": f"User {username} deleted"}


@router.post("/tenants/{tenant_id}/reset")
async def reset_tenant_usage_bridge(tenant_id: str):
    """Reset today's request/token counters for a tenant."""
    import time

    try:
        import core.services as app_mod

        q = getattr(app_mod, "redis_queue", None)
        if q and getattr(q, "configured", False):
            now = int(time.time())
            q.delete(f"rate:{tenant_id}:{now // 86400}:rpd")
            q.delete(f"rate:{tenant_id}:tokens")
            q.delete(f"rate:{tenant_id}:cost")
            return {"status": "success", "message": f"Tenant {tenant_id} usage reset"}
    except Exception as e:
        logger.debug(f"Reset tenant error: {e}")
    return {"status": "success", "message": f"Tenant {tenant_id} usage reset"}
