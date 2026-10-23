import os
for f in ("test.db",):
    if os.path.exists(f):
        os.remove(f)
os.environ.update(DATABASE_URL="sqlite:///./test.db", ADMIN_EMAIL="admin@test.io",
                  ADMIN_PASSWORD="Admin12345", ANTHROPIC_API_KEY="", N8N_WEBHOOK_URL="", UPLOAD_DIR="./test_uploads")
from fastapi.testclient import TestClient  # noqa: E402
from app import ai  # noqa: E402
from app.main import app  # noqa: E402


def auth(c, email, pw):
    r = c.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/api/customers").status_code == 401  # protected
        assert c.post("/api/auth/register", json={"email": "ag@test.io", "password": "Agent12345"}).status_code == 201
        assert c.post("/api/auth/register", json={"email": "ag@test.io", "password": "Agent12345"}).status_code == 409
        assert c.post("/api/auth/login", data={"username": "ag@test.io", "password": "bad"}).status_code == 401
        agent, admin = auth(c, "ag@test.io", "Agent12345"), auth(c, "admin@test.io", "Admin12345")

        cust = c.post("/api/customers", json={"name": "Amine", "email": "amine@x.dz"}, headers=agent).json()
        order = c.post("/api/orders", headers=agent, json={
            "customer_id": cust["id"], "title": "Site vitrine", "amount": 1200,
            "message": "Bonjour, il y a un retard et un problème avec ma facture. Urgent."}).json()
        assert order["status"] == "new"

        got = [o for o in c.get("/api/orders", headers=agent).json() if o["id"] == order["id"]][0]
        assert got["category"] == "complaint" and got["priority"] == "high"  # background AI ran

        assert c.patch(f"/api/orders/{order['id']}", json={"status": "done"}, headers=agent).json()["status"] == "done"
        assert c.delete(f"/api/customers/{cust['id']}", headers=agent).status_code == 403  # role check
        s = c.get("/api/stats", headers=agent).json()
        assert s["orders"] == 1 and s["revenue"] == 1200 and s["by_status"]["done"] == 1
        assert sum(s["monthly_revenue"]) == 1200 and s["revenue_this_month"] == 1200 and s["avg_order_value"] == 1200
        assert c.get("/api/users", headers=agent).status_code == 403
        assert len(c.get("/api/users", headers=admin).json()) == 2
        assert c.delete(f"/api/customers/{cust['id']}", headers=admin).status_code == 204


def test_ai_fallback():
    r = ai.analyze("Can I get a quote for 10 licenses? Price please.")
    assert r["category"] == "sales" and r["priority"] == "normal"


def test_login_throttle_and_search_escape():
    with TestClient(app) as c:
        for _ in range(5):
            assert c.post("/api/auth/login", data={"username": "admin@test.io", "password": "nope"}).status_code == 401
        assert c.post("/api/auth/login", data={"username": "admin@test.io", "password": "Admin12345"}).status_code == 429
        from app.cache import cache
        cache.clear()
        admin = auth(c, "admin@test.io", "Admin12345")
        c.post("/api/customers", json={"name": "100% Bio", "email": "bio@x.dz"}, headers=admin)
        c.post("/api/customers", json={"name": "Other", "email": "o@x.dz"}, headers=admin)
        found = c.get("/api/customers", params={"q": "%"}, headers=admin).json()
        assert [x["name"] for x in found] == ["100% Bio"]  # '%' is literal, not a wildcard


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_roles_profile_avatar_users_audit():
    with TestClient(app) as c:
        admin = auth(c, "admin@test.io", "Admin12345")
        c.post("/api/auth/register", json={"email": "ag2@test.io", "password": "Agent12345"})
        agent = auth(c, "ag2@test.io", "Agent12345")

        perms = c.get("/api/auth/me", headers=agent).json()["permissions"]
        assert "customers:write" in perms and "customers:delete" not in perms and "users:manage" not in perms

        # agent: add + modify yes, delete / admin areas no
        cust = c.post("/api/customers", json={"name": "Acme", "email": "a@acme.dz"}, headers=agent).json()
        r = c.put(f"/api/customers/{cust['id']}", json={"name": "Acme SARL", "email": "a@acme.dz"}, headers=agent)
        assert r.status_code == 200 and r.json()["name"] == "Acme SARL"
        order = c.post("/api/orders", json={"customer_id": cust["id"], "title": "T", "amount": 10}, headers=agent).json()
        assert c.patch(f"/api/orders/{order['id']}", json={"title": "T2", "amount": 12}, headers=agent).json()["title"] == "T2"
        assert c.delete(f"/api/orders/{order['id']}", headers=agent).status_code == 403
        assert c.delete(f"/api/customers/{cust['id']}", headers=agent).status_code == 403
        assert c.get("/api/users", headers=agent).status_code == 403
        assert c.get("/api/audit", headers=agent).status_code == 403

        # own profile + photo (type sniffed from bytes, not trusted from the client)
        assert c.patch("/api/users/me", json={"full_name": "Agent Two"}, headers=agent).json()["full_name"] == "Agent Two"
        r = c.post("/api/users/me/avatar", files={"file": ("x.png", PNG, "image/png")}, headers=agent)
        assert r.status_code == 200
        assert c.get(f"/api/avatars/{r.json()['avatar']}").status_code == 200
        fake = c.post("/api/users/me/avatar", files={"file": ("x.png", b"GIF89a" + b"0" * 20, "image/png")}, headers=agent)
        assert fake.status_code == 415
        assert c.get("/api/avatars/evil.png").status_code == 404

        # admin: delete, manage users, photos
        assert c.delete(f"/api/orders/{order['id']}", headers=admin).status_code == 204
        users = c.get("/api/users", headers=admin).json()
        uid = next(u["id"] for u in users if u["email"] == "ag2@test.io")
        admin_id = next(u["id"] for u in users if u["email"] == "admin@test.io")
        assert c.patch(f"/api/users/{uid}", json={"full_name": "Renamed", "phone": "0550"}, headers=admin).json()["phone"] == "0550"
        assert c.post(f"/api/users/{uid}/avatar", files={"file": ("y.png", PNG, "image/png")}, headers=admin).status_code == 200
        assert c.delete(f"/api/users/{uid}/avatar", headers=admin).json()["avatar"] is None
        assert c.delete(f"/api/users/{admin_id}", headers=admin).status_code == 400  # no self-delete
        assert c.patch(f"/api/users/{admin_id}", json={"role": "agent"}, headers=admin).status_code == 400
        made = c.post("/api/users", json={"email": "New@Test.io", "password": "Newpass123", "role": "agent"}, headers=admin)
        assert made.status_code == 201 and made.json()["email"] == "new@test.io"

        # a disabled account is locked out at once, even with a valid token
        assert c.patch(f"/api/users/{uid}", json={"is_active": False}, headers=admin).status_code == 200
        assert c.get("/api/auth/me", headers=agent).status_code == 401
        assert c.post("/api/auth/login", data={"username": "ag2@test.io", "password": "Agent12345"}).status_code == 403
        assert c.delete(f"/api/users/{uid}", headers=admin).status_code == 204

        actions = {a["action"] for a in c.get("/api/audit", headers=admin).json()}
        assert {"customer.update", "order.delete", "user.update", "user.delete", "avatar.set"} <= actions


def test_csv_export_blocks_formula_injection():
    with TestClient(app) as c:
        admin = auth(c, "admin@test.io", "Admin12345")
        c.post("/api/customers", json={"name": "=HYPERLINK(1)", "email": "evil@x.dz"}, headers=admin)
        body = c.get("/api/export/customers.csv", headers=admin).text
        assert "'=HYPERLINK(1)" in body
