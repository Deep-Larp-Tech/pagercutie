"""ASGI entrypoint for `fastapi dev` / `fastapi run`. Tests build their own app via `create_app(settings)`."""

from pagercutie.main import create_app

app = create_app()
