"""Where generated creatives live.

Files on a volume, not blobs in MySQL: a creative is served straight to an
`<img>` by the same origin that serves the console, and a row that has to be
decoded before it can be looked at is a row nobody looks at.
"""

from __future__ import annotations

import uuid
from pathlib import Path

#: The URL prefix these files are served under. Mounted in `app.main` before
#: the SPA catch-all, which owns `/` and would otherwise swallow it.
MEDIA_PREFIX = "/media"


class AssetStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        from app.workspace import principal
        actor = principal.get()
        prefix = f"w/{actor.workspace_id}/" if actor else ""
        name = f"{prefix}{uuid.uuid4().hex}{suffix}"
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_bytes(data)
        return f"{MEDIA_PREFIX}/{name}"

    def path_for(self, media_url: str) -> Path:
        if not media_url.startswith(f"{MEDIA_PREFIX}/"):
            raise ValueError(f"not a media url: {media_url!r}")

        from app.workspace import principal, require_media_scope
        name = media_url[len(MEDIA_PREFIX) + 1:]
        candidate = (self.root / name).resolve()
        # A stored url is generated, never user-supplied — but it reaches the
        # filesystem, so it is checked like it were.
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError(f"not a media url: {media_url!r}")
        if principal.get():
            require_media_scope(media_url)
        return candidate

    def read(self, media_url: str) -> bytes:
        return self.path_for(media_url).read_bytes()
