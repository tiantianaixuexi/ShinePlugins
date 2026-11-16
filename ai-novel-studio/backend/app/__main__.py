"""Allow ``python -m app`` from the backend directory.

This is the entry point the Tauri sidecar uses.
"""

from __future__ import annotations

from app.core.config import get_settings


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
