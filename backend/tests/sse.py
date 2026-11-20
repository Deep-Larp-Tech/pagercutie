import json
from typing import Any


def parse_sse(body: str) -> list[dict[str, Any]]:
    """JSON `data` of each event in a text/event-stream body; comments (keep-alive pings) are skipped."""
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data = [line.removeprefix("data:").removeprefix(" ") for line in block.split("\n") if line.startswith("data:")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events
