"""Database utilities — transaction manager with fallback."""
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession

logger = logging.getLogger(__name__)


class TransactionManager:
    """Manages MongoDB transactions with fallback.

    When transactions are enabled and available, wraps operations in a session.
    When not, provides compensation hooks for manual cleanup.

    Usage:
        tx = TransactionManager(db, enabled=True)
        async with tx as session:
            # do operations
            if session:
                # in transaction mode — operations use session
            # on success: auto-commit
        # on exception: auto-abort or run compensation
    """

    def __init__(self, db: AsyncIOMotorDatabase, enabled: bool = False):
        self.db = db
        self.enabled = enabled
        self.session: Optional[AsyncIOMotorClientSession] = None
        self._compensation_steps: list = []

    async def __aenter__(self) -> Optional[AsyncIOMotorClientSession]:
        if self.enabled:
            self.session = await self.db.client.start_session()
            self.session.start_transaction()
            return self.session
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            try:
                if exc_type:
                    await self.session.abort_transaction()
                else:
                    await self.session.commit_transaction()
            finally:
                await self.session.end_session()
        elif exc_type and not self.enabled:
            # Fallback mode with error — run compensation
            await self._run_compensation()

    def add_compensation(self, description: str, coro_func, *args, **kwargs):
        """Register a compensation step for fallback mode."""
        self._compensation_steps.append((description, coro_func, args, kwargs))

    async def _run_compensation(self):
        """Run all registered compensation steps in reverse order."""
        for desc, coro, args, kwargs in reversed(self._compensation_steps):
            try:
                await coro(*args, **kwargs)
                logger.info("Compensation OK: %s", desc)
            except Exception as e:
                logger.error("Compensation FAILED: %s: %s", desc, e)
