# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Refuse a request another site's page made, whatever address it came from."""

from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def cross_site_refusal(headers: Mapping[str, str]) -> str | None:
    """Why a request with these (lower-case) headers came from another
    site's page, or None when it came from this origin or from no page."""
    if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return "answers its own pages only"
    origin = headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != headers.get("host", ""):
        return "answers its own pages only"
    return None


def same_origin(request: Request) -> None:
    """A route dependency answering 403 to another site's page."""
    reason = cross_site_refusal(request.headers)
    if reason is not None:
        raise HTTPException(status_code=403, detail=f"this route {reason}")
