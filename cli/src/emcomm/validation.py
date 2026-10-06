"""JSON-schema validation for profile and definition files."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema


class ProfileError(Exception):
    """A profile or definition is missing or invalid."""


@cache
def _schema(kind: str) -> dict[str, Any]:
    return json.loads(resources.files("emcomm.schemas").joinpath(f"{kind}.schema.json").read_text())


def validate(kind: str, data: Any, where: Path | str) -> None:
    try:
        jsonschema.validate(data, _schema(kind))
    except jsonschema.ValidationError as exc:
        loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ProfileError(f"{where}: {loc}: {exc.message}") from None
