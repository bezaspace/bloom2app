"""FastAPI auth routes and dependency for the minimal SQLite auth system."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.database import (
    create_token,
    delete_token,
    get_user_by_token,
    register_user,
    verify_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    # Bare minimum: username and password only. No length or format rules.
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


class TokenPayload(BaseModel):
    username: str
    token: str


def _extract_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return token


async def get_current_user_token(
    authorization: str = Header(...),
) -> TokenPayload:
    token = _extract_token(authorization)
    username = await get_user_by_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return TokenPayload(username=username, token=token)


async def get_current_user(
    payload: TokenPayload = Depends(get_current_user_token),
) -> str:
    return payload.username


@router.post("/register", response_model=AuthResponse)
async def register(body: AuthRequest) -> AuthResponse:
    ok = await register_user(body.username, body.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    token = await create_token(body.username)
    return AuthResponse(token=token, username=body.username)


@router.post("/login", response_model=AuthResponse)
async def login(body: AuthRequest) -> AuthResponse:
    if not await verify_user(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = await create_token(body.username)
    return AuthResponse(token=token, username=body.username)


@router.post("/logout")
async def logout(payload: TokenPayload = Depends(get_current_user_token)) -> dict:
    await delete_token(payload.token)
    return {"ok": True}
