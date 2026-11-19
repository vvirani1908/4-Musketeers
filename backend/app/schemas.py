from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: UserRole
    created_at: datetime
