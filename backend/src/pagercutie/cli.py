"""`pagercutie --role=…`: starts the backend in one role or role group (SPEC §3.2)."""

import argparse
import sys

import uvicorn

from pagercutie.core.enums import Role, RoleGroup
from pagercutie.core.settings import Settings
from pagercutie.core.workers import WorkerGroup
from pagercutie.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="pagercutie", description=__doc__)
    parser.add_argument("--role", required=True, choices=[*Role, *RoleGroup], help="role or role group to run")
    parser.add_argument("--host", default="127.0.0.1", help="interface to listen on; containers pass 0.0.0.0")
    args = parser.parse_args()

    settings = Settings.model_validate({"roles": args.role})
    app = create_app(settings)
    # The app object (not an import string) keeps uvicorn at one process, so each consumer joins its group once.
    # `log_config=None` keeps the logging set up by `create_app`.
    uvicorn.run(
        app,
        host=args.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
        access_log=False,
    )
    workers: WorkerGroup | None = getattr(app.state, "workers", None)
    if workers and workers.failed:
        sys.exit(1)
