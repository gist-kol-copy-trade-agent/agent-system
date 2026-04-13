"""Application entrypoint for local bootstrap and smoke testing."""

from app.services.bootstrap import bootstrap_application


def main() -> None:
    bootstrap_application()


if __name__ == "__main__":
    main()
