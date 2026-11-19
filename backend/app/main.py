from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import authenticate_user, create_access_token, get_current_user, require_roles
from app.database import check_database_connection, get_db
from app.models import User, UserRole
from app.schemas import CurrentUser, Token

app = FastAPI(
    title="AI-Powered Enterprise Knowledge Portal API",
    version="0.1.0",
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Return the availability status of the backend service."""
    try:
        check_database_connection()
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    return {"status": "ok"}


@app.post("/api/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Authenticate a user and return a bearer access token."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(access_token=create_access_token(user), token_type="bearer")


@app.get("/api/auth/me", response_model=CurrentUser)
def current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's public profile."""
    return current_user


@app.get("/api/auth/admin-check")
def admin_check(current_user: User = Depends(require_roles(UserRole.ADMIN))) -> dict[str, str]:
    """Small protected endpoint demonstrating reusable role authorization."""
    return {"status": "ok", "role": current_user.role.value}
