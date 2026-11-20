import json
import sys
from pathlib import Path

from pagercutie.core.settings import Settings
from pagercutie.main import create_app

app = create_app(Settings(database_url="postgresql+asyncpg://contract@localhost/contract"))
Path(sys.argv[1]).write_text(json.dumps(app.openapi(), indent=2) + "\n")
