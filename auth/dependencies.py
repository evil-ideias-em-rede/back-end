import jwt
from auth.jwt_utils import decode_access_token
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


bearer_scheme = HTTPBearer()
optional_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, google_id: str | None = None):
        self.user_id = user_id
        self.google_id = google_id


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    return CurrentUser(user_id=payload["sub"], google_id=payload.get("google_id"))


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
) -> CurrentUser | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    return CurrentUser(user_id=payload["sub"], google_id=payload.get("google_id"))
