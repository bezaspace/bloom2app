"""FastAPI auth routes and dependency for practitioner accounts.

Mirrors ``app/auth.py`` but uses the separate ``practitioners`` and
``practitioner_tokens`` tables so patient and practitioner sessions never
collide.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.practitioner_db import (
    create_practitioner_token,
    delete_practitioner_token,
    get_practitioner_by_token,
    register_practitioner,
    update_practitioner_profile,
    verify_practitioner,
)

router = APIRouter(prefix="/practitioner/auth", tags=["practitioner-auth"])


class PractitionerRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1)
    title: str | None = None
    specialization: str | None = None
    bio: str | None = None
    email: str | None = None
    phone: str | None = None
    years_experience: int | None = None
    consultation_fee: float | None = None


class PractitionerLoginRequest(BaseModel):
    username: str
    password: str


class PractitionerAuthResponse(BaseModel):
    token: str
    practitioner: dict


class PractitionerTokenPayload(BaseModel):
    practitioner_id: int
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


async def get_current_practitioner_token(
    authorization: str = Header(...),
) -> PractitionerTokenPayload:
    token = _extract_token(authorization)
    p = await get_practitioner_by_token(token)
    if not p:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired practitioner token",
        )
    return PractitionerTokenPayload(
        practitioner_id=p["id"], username=p["username"], token=token
    )


async def get_current_practitioner_id(
    payload: PractitionerTokenPayload = Depends(get_current_practitioner_token),
) -> int:
    return payload.practitioner_id


@router.post("/register", response_model=PractitionerAuthResponse)
async def register(body: PractitionerRegisterRequest) -> PractitionerAuthResponse:
    p = await register_practitioner(body.model_dump())
    if not p:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Practitioner username already exists",
        )
    token = await create_practitioner_token(p["id"])
    return PractitionerAuthResponse(token=token, practitioner=p)


@router.post("/login", response_model=PractitionerAuthResponse)
async def login(body: PractitionerLoginRequest) -> PractitionerAuthResponse:
    p = await verify_practitioner(body.username, body.password)
    if not p:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = await create_practitioner_token(p["id"])
    from app.practitioner_db import get_practitioner_by_id
    full = await get_practitioner_by_id(p["id"])
    # full is the public dict (no secrets) from _public_practitioner.
    return PractitionerAuthResponse(token=token, practitioner=full)


@router.post("/logout")
async def logout(
    payload: PractitionerTokenPayload = Depends(get_current_practitioner_token),
) -> dict:
    await delete_practitioner_token(payload.token)
    return {"ok": True}


class PractitionerProfileUpdate(BaseModel):
    full_name: str | None = None
    title: str | None = None
    specialization: str | None = None
    bio: str | None = None
    email: str | None = None
    phone: str | None = None
    years_experience: int | None = None
    consultation_fee: float | None = None


@router.put("/profile", response_model=dict)
async def update_profile(
    body: PractitionerProfileUpdate,
    payload: PractitionerTokenPayload = Depends(get_current_practitioner_token),
) -> dict:
    """Update the current practitioner's editable profile fields."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        from app.practitioner_db import get_practitioner_by_id
        return await get_practitioner_by_id(payload.practitioner_id)
    updated = await update_practitioner_profile(payload.practitioner_id, updates)
    return updated
