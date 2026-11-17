from fastapi import FastAPI

app = FastAPI(
    title="AI-Powered Enterprise Knowledge Portal API",
    version="0.1.0",
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Return the availability status of the backend service."""
    return {"status": "ok"}
