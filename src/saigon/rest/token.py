import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Awaitable, Callable


__all__ = [
    'AsyncManagedToken',
    'TokenManager'
]

logger = logging.getLogger(__name__)


class AsyncManagedToken[TokenType]:

    def __init__(self):
        self._access_token: Optional[TokenType] = None
        self._token_expires_in = datetime.now(tz=timezone.utc)
        self._lock = asyncio.Lock()

    def get(self) -> Optional[TokenType]:
        return self._access_token

    @property
    def needs_refresh(self) -> bool:
        """Check if the token has expired or doesn't exist."""
        return self._token_expires_in <= datetime.now(tz=timezone.utc)

    async def __aenter__(self):
        await self._lock.acquire()
        return None

    async def __aexit__(self, exc_type, exc, tb):
        self._lock.release()

    def update(
        self, access_token: TokenType, token_expires_in: datetime
    ):
        logger.debug(f"Update access token with expiration: {token_expires_in}")
        self._access_token = access_token
        self._token_expires_in = token_expires_in


class TokenManager[TokenType]:
    def __init__(
            self,
            token_expiry: timedelta,
            managed_token: Optional[AsyncManagedToken[TokenType]] = None
    ):
        self._token_expiry = token_expiry
        self._managed_token = managed_token or AsyncManagedToken()

    async def reuse_or_refresh[RequestType](
            self,
            request_access_token: Callable[[RequestType], Awaitable[TokenType]],
            request: RequestType
    ) -> Optional[TokenType]:
        if self._managed_token.needs_refresh:
            async with self._managed_token:
                if self._managed_token.needs_refresh:
                    logger.debug('Refreshing access token')
                    current_time = datetime.now(tz=timezone.utc)
                    access_token = await request_access_token(request)
                    self._managed_token.update(
                        access_token,
                        current_time + self._token_expiry
                    )
                else:
                    access_token = self._managed_token.get()
        else:
            access_token = self._managed_token.get()

        return access_token
