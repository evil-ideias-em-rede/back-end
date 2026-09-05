from db.pool import get_pool
from auth.jwt_utils import create_access_token
from auth.google_auth import verify_google_token
from db.queries import get_or_create_user_by_google
from schemas import GoogleLoginIn, LoginOut
from fastapi import APIRouter, HTTPException, status


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=LoginOut)
async def login_google(body: GoogleLoginIn):
    try:
        user_data = verify_google_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    pool = get_pool()
    async with pool.acquire() as conn:
        user = await get_or_create_user_by_google(conn, **user_data)

    access_token = create_access_token(user_id=str(user["id"]), google_id=user["google_id"])

    return LoginOut(
        access_token=access_token,
        user_id=user["id"],
        email=user["email"],
        name=user["name"],
        picture_url=user["picture_url"],
    )
