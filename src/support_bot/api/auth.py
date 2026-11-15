import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .. import config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    if not config.API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Server API key not configured")
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key",
                            headers={"WWW-Authenticate": "APIKey"})
    if not secrets.compare_digest(api_key.encode(), config.API_KEY.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API key")
