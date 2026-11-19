from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database_connection

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
