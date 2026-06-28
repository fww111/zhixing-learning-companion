from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import TokenResponse, User, UserCreate, UserLogin, UserRead


class DuplicateUserError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: UserCreate) -> TokenResponse:
        existing = self.db.scalar(
            select(User).where(or_(User.username == payload.username, User.email == payload.email))
        )
        if existing:
            raise DuplicateUserError()

        user = User(
            username=payload.username,
            email=str(payload.email),
            password_hash=hash_password(payload.password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._token_response(user)

    def login(self, payload: UserLogin) -> TokenResponse:
        user = self.db.scalar(select(User).where(or_(User.username == payload.account, User.email == payload.account)))
        if not user or not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError()
        return self._token_response(user)

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def _token_response(self, user: User) -> TokenResponse:
        token = create_access_token(str(user.id), {"username": user.username})
        return TokenResponse(access_token=token, user=UserRead.model_validate(user))
