import os
from datetime import datetime, timedelta, timezone

import jwt


JWT_SECRET = os.getenv("JWT_SECRET") or "desenvolvimento-troque-este-segredo"
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES") or "1440")


def create_access_token(*, user_id: str, google_id: str | None = None) -> str:
    payload = {
        "sub": user_id,
        "google_id": google_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
