from __future__ import annotations

import re


KEY_PATTERN = re.compile(r"^[a-z0-9]+([._-][a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def require_key(value: str, *, field: str) -> str:
    if not KEY_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must match {KEY_PATTERN.pattern}: {value!r}")
    return value


def require_version(value: str, *, field: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must match {VERSION_PATTERN.pattern}: {value!r}")
    return value


def require_sha256(value: str, *, field: str) -> str:
    if not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest: {value!r}")
    return value
