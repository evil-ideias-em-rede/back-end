import os
from google.oauth2 import id_token
from google.auth.transport import requests as grequests


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def verify_google_token(token: str) -> dict:
    """
    Valida o ID token enviado pelo frontend (Google Sign-In).
    Lança ValueError se o token for inválido, expirado ou de outro client_id.
    """
    try:
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise ValueError(f"Token do Google inválido: {exc}") from exc

    if idinfo.get("aud") != GOOGLE_CLIENT_ID:
        raise ValueError("Token com audience inválida")

    return {
        "google_id": idinfo["sub"],
        "email": idinfo.get("email"),
        "name": idinfo.get("name"),
        "picture_url": idinfo.get("picture"),
    }
