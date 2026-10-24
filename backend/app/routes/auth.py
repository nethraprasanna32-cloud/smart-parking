import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.app.services.auth import COOKIE_NAME, SESSION_SECONDS
from backend.app.state import auth


router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


class LoginRequest(BaseModel):
    password: str


@router.get("/status")
def auth_status(request: Request):
    headers = {key.lower(): value for key, value in request.headers.items()}
    return {
        "required": auth.enabled,
        "signed_in": auth.request_allowed(headers),
    }


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    if not auth.enabled:
        return {"signed_in": True, "required": False}

    if not auth.check_password(request.password):
        await asyncio.sleep(1)
        raise HTTPException(401, "Wrong password.")

    response.set_cookie(
        COOKIE_NAME,
        auth.make_token(),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {"signed_in": True, "required": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"signed_in": False, "required": auth.enabled}
