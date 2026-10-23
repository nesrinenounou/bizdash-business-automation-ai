import hashlib, hmac, os
from datetime import datetime, timedelta, timezone
import jwt
from .cache import cache
from .config import settings

SECRET = settings.secret_key
if settings.env == "production" and (len(SECRET) < 32 or SECRET == "dev-secret-change-me"):
    raise RuntimeError("SECRET_KEY must be at least 32 random characters in production")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"{salt.hex()}${hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200_000).hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(check.hex(), digest)


def create_token(email: str, role: str, minutes: int = 480) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": email, "role": role, "exp": exp}, SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"])


# Login throttling lives in the shared cache, so it holds across several API replicas when Redis is on.
def throttled(key: str) -> bool:
    return int(cache.get(f"fail:{key}") or 0) >= settings.login_max_failures


def record_failure(key: str) -> None:
    cache.incr(f"fail:{key}", settings.login_window)


def clear_failures(key: str) -> None:
    cache.delete(f"fail:{key}")
