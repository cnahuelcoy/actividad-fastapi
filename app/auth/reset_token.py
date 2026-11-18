from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.shared.config import RESET_TOKEN_EXPIRE_MINUTES, RESET_TOKEN_SECRET
from app.shared.datetimes import utc_now

RESET_TOKEN_PURPOSE = "password_reset"
ALGORITHM = "HS256"


def create_reset_token(user_id: UUID) -> tuple[str, str, datetime]:
    jti = str(uuid4())
    expires_at = utc_now() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": jti,
            "purpose": RESET_TOKEN_PURPOSE,
            "exp": expires_at,
        },
        RESET_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )
    return token, jti, expires_at
