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


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_by: int
    created_at: datetime
    processing_status: str
    processing_error: str | None = None


class SearchResult(BaseModel):
    document_id: int
    title: str
    snippet: str
    page_number: int | None = None
    similarity: float
