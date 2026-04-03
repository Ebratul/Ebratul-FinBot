"""
In-memory user store with JWT authentication for FinBot demo.
Provides 5 demo accounts (one per role) + 1 admin account.
"""

import hashlib
import hmac
import json
import time
import uuid
from typing import Optional, Dict, List


# ── JWT Secret (demo only — in production use a proper secret) ────────────────
JWT_SECRET = "finbot-demo-secret-key-2024"
JWT_EXPIRY_SECONDS = 86400  # 24 hours


# ── Role → Collection Access Mapping ─────────────────────────────────────────
ROLE_COLLECTIONS = {
    "employee":    ["general"],
    "finance":     ["general", "finance"],
    "engineering": ["general", "engineering"],
    "marketing":   ["general", "marketing"],
    "c_level":     ["general", "finance", "engineering", "marketing"],
}


def _hash_password(password: str) -> str:
    """Simple SHA-256 hash for demo purposes."""
    return hashlib.sha256(password.encode()).hexdigest()


class User:
    def __init__(self, username: str, password: str, role: str, display_name: str, is_admin: bool = False):
        self.id = f"u_{username}"
        self.username = username
        self.password_hash = _hash_password(password)
        self.role = role
        self.display_name = display_name
        self.is_admin = is_admin

    def verify_password(self, password: str) -> bool:
        return self.password_hash == _hash_password(password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name,
            "is_admin": self.is_admin,
            "accessible_collections": ROLE_COLLECTIONS.get(self.role, ["general"]),
        }


class UserStore:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._seed_demo_users()

    def _seed_demo_users(self):
        """Create the 5 demo accounts + 1 admin."""
        demo_users = [
            ("alice",  "demo123", "employee",    "Alice Johnson"),
            ("bob",    "demo123", "finance",     "Bob Williams"),
            ("carol",  "demo123", "engineering", "Carol Martinez"),
            ("dave",   "demo123", "marketing",   "Dave Thompson"),
            ("eve",    "demo123", "c_level",     "Eve Chen (CEO)"),
            ("admin",  "admin123", "c_level",    "System Admin"),
        ]
        for username, password, role, display_name in demo_users:
            user = User(username, password, role, display_name, is_admin=(username == "admin"))
            self.users[user.id] = user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        for user in self.users.values():
            if user.username == username and user.verify_password(password):
                return user
        return None

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def get_all(self) -> List[dict]:
        return [u.to_dict() for u in self.users.values()]

    def create_user(self, username: str, password: str, role: str, display_name: str) -> Optional[User]:
        # Check for duplicate username
        for u in self.users.values():
            if u.username == username:
                return None
        user = User(username, password, role, display_name)
        self.users[user.id] = user
        return user

    def delete_user(self, user_id: str) -> bool:
        if user_id in self.users:
            del self.users[user_id]
            return True
        return False

    def update_role(self, user_id: str, new_role: str) -> Optional[User]:
        user = self.users.get(user_id)
        if user and new_role in ROLE_COLLECTIONS:
            user.role = new_role
            return user
        return None


# ── JWT Helpers ───────────────────────────────────────────────────────────────

def _b64_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(s: str) -> bytes:
    import base64
    padding = 4 - len(s) % 4
    s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_token(user: User) -> str:
    """Create a simple HMAC-signed JWT token."""
    header = _b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64_encode(json.dumps({
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.is_admin,
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }).encode())
    signature = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"{header}.{payload}.{signature}"


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token. Returns payload dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, signature = parts
        expected_sig = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        data = json.loads(_b64_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# Singleton
user_store = UserStore()
