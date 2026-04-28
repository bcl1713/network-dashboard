from fastapi import Header, HTTPException, status

from .config import get_settings


async def require_api_token(x_api_token: str | None = Header(default=None)) -> None:
    """Reject requests without a matching X-API-Token header.

    Health endpoints opt out by not declaring this dependency.
    """
    settings = get_settings()
    if not x_api_token or x_api_token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Token",
        )
