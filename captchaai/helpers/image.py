# ── What this file IS ─────────────────────────────────────────────────────────
# The image resolver: converts whatever image the caller gave us (file path, URL,
# or raw base64) into the wire format the API wants. It exists so image captcha
# types accept flexible input while the API always receives the correct fields.
# It runs ONLY when the registry entry says has_image is True.

from __future__ import annotations

import base64
import binascii
import struct
from pathlib import Path

import httpx

from ..core.registry import CaptchaTypeEntry
from ..exceptions import ValidationError

# Conservative SDK-side guard. The API also enforces its own limit and will
# return ERROR_IMAGE_DIMENSIONS_TOO_LARGE (mapped to ValidationError via
# _SUBMIT_FATAL) for anything that slips through, but catching here avoids the
# wasted API round-trip and the risk of a payload-too-large HTTP 413 before
# the API can even return a structured error code.
_MAX_IMAGE_DIMENSION = 1000


def resolve(params: dict, entry: CaptchaTypeEntry) -> None:
    """Resolve image input into API-ready fields, in place.

    Handles the single-image case here (`image` param). Multi-image types (BLS)
    are resolved by `_resolve_many` into `image_base64_N` data-URI fields.

    Parameters:
        params: the params dict; the raw image lives under `image` (or `images`).
        entry: the registry row (already known to have has_image=True).

    Raises:
        ValidationError: if the input is missing or is not a path, URL, or base64.
    """
    # BLS carries a list under `images`; each cell becomes a numbered data URI.
    if "images" in params:
        _resolve_many(params)
        return

    # Single-image types: pull `image`, convert, and store as base64 `body`.
    src = params.pop("image", None)
    if src is None:
        raise ValidationError(f"{entry.name}: 'image' is required")
    params["body"] = _to_base64(src)


def _resolve_many(params: dict) -> None:
    """Convert a list of images into numbered BLS data-URI fields.

    The API requires image_base64_1 … image_base64_9, each as
    `data:image/png;base64,...` (or gif). All nine cells must be supplied.
    """
    images = params.pop("images")
    if not isinstance(images, (list, tuple)) or not images:
        raise ValidationError("'images' must be a non-empty list")
    if len(images) != 9:
        raise ValidationError("BLS requires exactly 9 images (one per grid cell)")
    # Number each image from 1 as the API expects (image_base64_1, …).
    for index, src in enumerate(images, start=1):
        params[f"image_base64_{index}"] = _to_data_uri(src)


def _to_data_uri(src: str | bytes, mime: str = "image/png") -> str:
    """Wrap one image as a base64 data URI string (required by the BLS API)."""
    return f"data:{mime};base64,{_to_base64(src)}"


def _check_image_dimensions(raw_bytes: bytes) -> None:
    """Raise ValidationError if the image dimensions exceed _MAX_IMAGE_DIMENSION.

    Reads width/height directly from the file header — no image library needed.
    Supports PNG and GIF (the two formats the BLS API accepts). Other formats
    are silently skipped; the API will catch them with its own dimension check.

    PNG layout:  8-byte signature, then IHDR chunk. Width (big-endian uint32)
                 at offset 16, height at offset 20.
    GIF layout:  6-byte signature ("GIF87a" / "GIF89a"). Width (little-endian
                 uint16) at offset 6, height at offset 8.
    """
    if len(raw_bytes) < 10:
        return  # too short to hold any recognised header; let the API decide

    # PNG: 8-byte magic b"\x89PNG\r\n\x1a\n"
    if len(raw_bytes) >= 24 and raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", raw_bytes[16:24])
        if width > _MAX_IMAGE_DIMENSION or height > _MAX_IMAGE_DIMENSION:
            raise ValidationError(
                f"Image dimensions {width}\u00d7{height} exceed the "
                f"{_MAX_IMAGE_DIMENSION}px per-side limit"
            )
        return

    # GIF87a / GIF89a
    if raw_bytes[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", raw_bytes[6:10])
        if width > _MAX_IMAGE_DIMENSION or height > _MAX_IMAGE_DIMENSION:
            raise ValidationError(
                f"Image dimensions {width}\u00d7{height} exceed the "
                f"{_MAX_IMAGE_DIMENSION}px per-side limit"
            )


def _to_base64(src: str | bytes) -> str:
    """Turn one image (path / URL / data-URI / raw base64 / bytes) into base64 text.

    Detection order:
        - bytes            → base64-encode directly
        - http(s):// URL   → download then base64-encode
        - data:...;base64  → strip the data-URI header, keep the payload
        - existing file    → read then base64-encode
        - otherwise        → assume it is already raw base64 if it looks valid

    Note: URL download is a one-off synchronous fetch. Image-by-URL is rare and
    this keeps the transport limited to its single request_raw method; the brief
    blocking cost is an accepted trade-off.

    Raises:
        ValidationError: if the input matches none of the supported forms.
    """
    # Raw bytes: check dimensions, then encode straight to base64 text.
    if isinstance(src, bytes):
        _check_image_dimensions(src)
        return base64.b64encode(src).decode("ascii")

    s = src.strip()

    # Remote URL: download the bytes, check dimensions, then encode.
    if s.startswith("http://") or s.startswith("https://"):
        try:
            data = httpx.get(s, timeout=30.0).content
        except Exception as exc:
            raise ValidationError(f"Failed to download image from URL: {exc}")
        _check_image_dimensions(data)
        return base64.b64encode(data).decode("ascii")

    # Data-URI: decode payload and check dimensions before forwarding.
    if s.startswith("data:") and "," in s:
        payload = s.split(",", 1)[1]
        _check_image_dimensions(base64.b64decode(payload))
        return payload

    # Local file path: read the file, check dimensions, then encode.
    path = Path(s)
    if path.exists() and path.is_file():
        data = path.read_bytes()
        _check_image_dimensions(data)
        return base64.b64encode(data).decode("ascii")

    # Last resort: maybe the caller already passed valid base64 text.
    # Decode to bytes so the dimension check can inspect the image header.
    if _looks_base64(s):
        _check_image_dimensions(base64.b64decode(s))
        return s

    raise ValidationError(
        "Unsupported image input: expected a file path, URL, data-URI, or base64 string"
    )


def _looks_base64(value: str) -> bool:
    """Return True if the string decodes cleanly as base64.

    Used as the final fallback so a caller can pass pre-encoded base64 directly.
    """
    try:
        # validate=True rejects strings containing non-base64 characters.
        base64.b64decode(value, validate=True)
        return True
    except (binascii.Error, ValueError):
        return False
