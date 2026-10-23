"""Role-based access control: one table says who can do what. Routes only ask for a permission."""
from enum import Enum


class Perm(str, Enum):
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_WRITE = "customers:write"      # create + edit
    CUSTOMERS_DELETE = "customers:delete"
    ORDERS_READ = "orders:read"
    ORDERS_WRITE = "orders:write"            # create + edit + change status
    ORDERS_DELETE = "orders:delete"
    STATS_READ = "stats:read"
    EXPORT_CSV = "export:csv"
    AI_ANALYZE = "ai:analyze"
    USERS_MANAGE = "users:manage"            # list, create, edit, delete users and their photos
    AUDIT_READ = "audit:read"


AGENT = frozenset({Perm.CUSTOMERS_READ, Perm.CUSTOMERS_WRITE, Perm.ORDERS_READ, Perm.ORDERS_WRITE,
                   Perm.STATS_READ, Perm.EXPORT_CSV, Perm.AI_ANALYZE})
ROLE_PERMS = {"agent": AGENT, "admin": frozenset(Perm)}


def perms_for(role: str) -> frozenset:
    return ROLE_PERMS.get(role, frozenset())
