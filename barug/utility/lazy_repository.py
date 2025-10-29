import threading
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class LazyRepositoryProxy:
    """Lazy proxy for any repository instance.

    Provide a repo_factory callable that returns the real repo (e.g. RepoClass(ConnectionAdapter())).
    The repo is created on first attribute access and cached thereafter.
    """

    def __init__(self, repo_factory: Callable[[], Any]) -> None:
        if not callable(repo_factory):
            raise TypeError("repo_factory must be callable")
        self._repo_factory = repo_factory
        self._repo = None
        self._lock = threading.Lock()

    def _ensure(self) -> None:
        # Double-checked locking: avoid acquiring lock once repo exists.
        if self._repo is None:
            with self._lock:
                if self._repo is None:
                    try:
                        # Only log high-level events (no sensitive data).
                        logger.debug("Creating repository instance (lazy)")
                        self._repo = self._repo_factory()
                        # Log only the type name to avoid leaking internal state/credentials
                        repo_type = type(self._repo).__name__ if self._repo is not None else "<none>"
                        logger.info("Lazy repository created: %s", repo_type)
                    except Exception as exc:
                        # Avoid logging exception message/args which may contain sensitive info.
                        logger.error("Repository factory raised %s during lazy initialization", type(exc).__name__)
                        # Re-raise the original exception to preserve behavior.
                        raise

    def __getattr__(self, name: str):
        # do not log attribute values or request-level data here
        logger.debug("LazyRepositoryProxy.__getattr__ access: %s", name)
        self._ensure()
        return getattr(self._repo, name)

    def __dir__(self):
        # expose attributes from proxy + underlying repo (if created)
        attrs = set(super().__dir__())
        if self._repo is not None:
            attrs.update(dir(self._repo))
        return sorted(attrs)

    def __repr__(self):
        if self._repo is None:
            return f"<LazyRepositoryProxy (not initialized) factory={self._repo_factory}>"
        return f"<LazyRepositoryProxy wrapping={self._repo!r}>"

    def close(self):
        """Optional: call close() on underlying repo/adapter if present."""
        if self._repo is None:
            return
        close = getattr(self._repo, "close", None)
        if callable(close):
            try:
                logger.debug("Closing underlying repository of type %s", type(self._repo).__name__)
                close()
                logger.info("Underlying repository closed")
            except Exception as exc:
                # Log only the exception type to avoid leaking details (stack trace may be sensitive).
                logger.warning("Closing repository raised %s", type(exc).__name__)
                # swallow exception to avoid raising during shutdown
                return