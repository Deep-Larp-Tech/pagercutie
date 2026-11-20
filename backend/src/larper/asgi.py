"""ASGI entrypoint for `fastapi dev` / `fastapi run`. Tests build their own app via `create_app(settings)`."""

from larper.main import create_app

app = create_app()
