from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.core.db import UnitOfWork, get_uow
from app.core.errors import UnauthorizedError, problem_responses
from app.modules.identity.facade import AuthUser, current_user
from app.modules.identity.models import User
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import LoginIn, RegisterIn, UserOut
from app.modules.identity.security import create_access_token
from app.modules.identity.service import IdentityService

router = APIRouter(tags=["identity"], responses=problem_responses(422))

Uow = Annotated[UnitOfWork, Depends(get_uow)]


def _set_auth_cookie(request: Request, response: Response, user: User) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user.id, user.role),
        max_age=settings.auth_token_ttl_minutes * 60,
        httponly=True,  # недоступна из JS — защита токена от XSS
        samesite="lax",  # не отправляется в кросс-сайтовых POST — защита от CSRF
        # За nginx схема берётся из X-Forwarded-Proto: по HTTPS cookie помечается Secure.
        secure=request.url.scheme == "https",
        path="/api",
    )


@router.post(
    "/auth/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(409),
)
async def register(body: RegisterIn, request: Request, response: Response, uow: Uow) -> User:
    """Регистрация. Пользователь сразу оказывается авторизованным."""
    user = await IdentityService(uow).register(
        email=body.email, name=body.name, password=body.password
    )
    await uow.commit()
    _set_auth_cookie(request, response, user)
    return user


@router.post(
    "/auth/login",
    response_model=UserOut,
    responses=problem_responses(401),
)
async def login(body: LoginIn, request: Request, response: Response, uow: Uow) -> User:
    user = await IdentityService(uow).authenticate(email=body.email, password=body.password)
    _set_auth_cookie(request, response, user)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(settings.auth_cookie_name, path="/api")


@router.get("/me", response_model=UserOut, responses=problem_responses(401))
async def me(auth: Annotated[AuthUser, Depends(current_user)], uow: Uow) -> User:
    user = await UserRepository(uow.session).get(auth.id)
    if user is None:  # пользователь удалён, а токен ещё жив
        raise UnauthorizedError()
    return user
