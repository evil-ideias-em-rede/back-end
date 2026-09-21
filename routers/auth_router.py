import re

import asyncpg
from db.pool import init_pool
from auth.dependencies import CurrentUser, get_current_user
from auth.jwt_utils import create_access_token
from auth.google_auth import verify_google_token
from auth.passwords import hash_password, verify_password
from db.queries import (
    create_password_user,
    get_or_create_user_by_google,
    get_user_by_email,
    get_user_by_id,
    list_user_schools,
    replace_user_schools,
    update_user_profile,
)
from schemas import (
    GoogleLoginIn,
    LoginOut,
    PasswordLoginIn,
    PasswordRegisterIn,
    ProfileUpdateIn,
    UserOut,
)
from fastapi import APIRouter, Depends, HTTPException, status


router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="E-mail inválido")
    return email


def _login_response(user) -> LoginOut:
    return LoginOut(
        access_token=create_access_token(
            user_id=str(user["id"]),
            google_id=user["google_id"],
        ),
        user_id=user["id"],
        email=user["email"],
        name=user["name"],
        picture_url=user["picture_url"],
    )


def _user_response(user, schools) -> UserOut:
    return UserOut(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        picture_url=user["picture_url"],
        schools=[row["name"] for row in schools],
    )


@router.post("/google", response_model=LoginOut)
async def login_google(body: GoogleLoginIn):
    try:
        user_data = verify_google_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    pool = await init_pool()
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


@router.post("/register", response_model=LoginOut, status_code=status.HTTP_201_CREATED)
async def register(body: PasswordRegisterIn):
    email = _normalize_email(body.email)
    pool = await init_pool()
    async with pool.acquire() as conn:
        if await get_user_by_email(conn, email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
        try:
            user = await create_password_user(
                conn,
                email=email,
                password_hash=hash_password(body.password),
                name=body.name.strip() if body.name else None,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado") from exc
    return _login_response(user)


@router.post("/login", response_model=LoginOut)
async def login(body: PasswordLoginIn):
    email = _normalize_email(body.email)
    pool = await init_pool()
    async with pool.acquire() as conn:
        user = await get_user_by_email(conn, email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos")
    return _login_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)):
    pool = await init_pool()
    async with pool.acquire() as conn:
        row = await get_user_by_id(conn, user.user_id)
        schools = await list_user_schools(conn, user.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    return _user_response(row, schools)


@router.patch("/me", response_model=UserOut)
async def update_me(body: ProfileUpdateIn, user: CurrentUser = Depends(get_current_user)):
    email = _normalize_email(body.email) if body.email else None
    school_names = []
    seen = set()
    for value in body.schools:
        name = value.strip()
        if not name:
            continue
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            school_names.append(name)

    pool = await init_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await update_user_profile(
                    conn,
                    user.user_id,
                    email,
                    body.name.strip() if body.name else None,
                    body.picture_url,
                )
                if row is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
                await replace_user_schools(conn, user.user_id, school_names)
                schools = await list_user_schools(conn, user.user_id)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado") from exc
    return _user_response(row, schools)
