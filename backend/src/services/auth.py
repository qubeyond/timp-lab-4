from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials

from src.config import Settings

REFRESH_COOKIE = "refresh_token"


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_token(self, fingerprint: str, role: str = "user", room_id: str | None = None) -> str:
        payload = {
            "sub": fingerprint,
            "role": role,
            "room_id": room_id,
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=self._settings.jwt_expire_minutes),
        }
        return jwt.encode(
            payload, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm
        )

    def create_refresh_token(self, fingerprint: str) -> str:
        payload = {
            "sub": fingerprint,
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
        }
        return jwt.encode(
            payload, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm
        )

    def set_refresh_cookie(self, response: Response, fingerprint: str) -> None:
        token = self.create_refresh_token(fingerprint)
        response.set_cookie(
            key=REFRESH_COOKIE,
            value=token,
            httponly=True,
            secure=not self._settings.debug,
            samesite="strict",
            max_age=self._settings.refresh_token_expire_days * 86400,
            path="/api/v1/auth",
        )

    def decode_token(self, token: str) -> dict:
        try:
            return jwt.decode(
                token, self._settings.jwt_secret, algorithms=[self._settings.jwt_algorithm]
            )
        except jwt.ExpiredSignatureError as e:
            raise HTTPException(status_code=401, detail="Токен истёк") from e
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail="Невалидный токен") from e

    def verify_user(self, credentials: HTTPAuthorizationCredentials | None) -> dict:
        if not credentials:
            raise HTTPException(status_code=401, detail="Требуется авторизация")
        payload = self.decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Невалидный тип токена")
        return payload

    def verify_admin(self, user: dict) -> dict:
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Требуются права администратора")
        return user
