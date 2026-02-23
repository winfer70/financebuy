"""
JWT bearer dependency — inject with Depends(get_current_user).
Returns the user_id (UUID string) from the token subject.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from .auth import JWT_SECRET, JWT_ALG

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Returns user_id string; raises 401 if token is missing or invalid."""
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError("No subject in token")
        return user_id
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
