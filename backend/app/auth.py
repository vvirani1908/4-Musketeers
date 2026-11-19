import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole


password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("invalid-login-placeholder")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """Hash a password using the recommended Argon2 configuration."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    return password_hash.verify(password, hashed_password)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the matching user, or None for invalid credentials."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        password_hash.verify(password, dummy_password_hash)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(user: User) -> str:
    """Create a short-lived JWT containing the user's identity and role."""
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    expires_in = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=expires_in),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode a bearer token and load the current user from the database."""
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        subject = payload.get("sub")
        user_id = int(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise credentials_exception() from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception()
    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Build a dependency that allows only users with one of the given roles."""
    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_dependency
