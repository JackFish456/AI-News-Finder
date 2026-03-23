from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def item_cache_key(prefix: str, parts: dict[str, Any]) -> str:
    return sha256_hex(prefix + "|" + stable_json(parts))[:32]
