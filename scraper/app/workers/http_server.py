from __future__ import annotations

import uvicorn

from app.config import get_settings
from app.http_app import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(), host=settings.scraper_host, port=settings.scraper_port)


if __name__ == "__main__":
    main()
