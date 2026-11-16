"""Encrypted storage for provider API keys.

Keys never go into SQLite: the database only stores the *label* of a secret.
This module keeps the actual values in ``secrets.json`` inside the application
data directory:

* **Windows** — every value is encrypted with DPAPI
  (``CryptProtectData``), which binds the ciphertext to the current Windows
  account. Copying the file to another machine or user yields nothing.
* **Other platforms** — the file is written with owner-only permissions and the
  values are stored base64-encoded. That is obfuscation, not encryption, so the
  docs tell non-Windows users to rely on OS keychains instead.

The file is replaced atomically (temp file + ``os.replace``) so a crash while
saving cannot truncate the user's keys.
"""

from __future__ import annotations

import base64
import contextlib
import ctypes
import json
import os
import sys
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

SECRETS_FILE = "secrets.json"
SECRET_SEPARATOR = "."


def _dpapi_available() -> bool:
    return sys.platform == "win32"


class _DataBlob(ctypes.Structure):
    """Mirror of Win32 ``DATA_BLOB``."""

    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _load_crypt32():
    from ctypes import wintypes

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _blob_from_bytes(crypt32, data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _read_and_free(kernel32, blob: _DataBlob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob.pbData:
            kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def protect(plaintext: str) -> str:
    """Encrypt *plaintext* and return a base64 token."""
    if not _dpapi_available():
        return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    crypt32, kernel32 = _load_crypt32()
    raw = plaintext.encode("utf-8")
    blob_in = _blob_from_bytes(crypt32, raw)
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError(f"CryptProtectData failed with {ctypes.get_last_error()}")
    return base64.b64encode(_read_and_free(kernel32, blob_out)).decode("ascii")


def unprotect(token: str) -> str:
    """Decrypt a token produced by :func:`protect`."""
    payload = base64.b64decode(token.encode("ascii"))
    if not _dpapi_available():
        return payload.decode("utf-8")

    crypt32, kernel32 = _load_crypt32()
    blob_in = _blob_from_bytes(crypt32, payload)
    blob_out = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed with {ctypes.get_last_error()}")
    return _read_and_free(kernel32, blob_out).decode("utf-8")


class SecretStore:
    """Label → secret mapping backed by an encrypted JSON file."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SECRETS_FILE
        self.encrypted = _dpapi_available()
        if not self.encrypted:
            logger.warning(
                "secret_store_unencrypted",
                detail="DPAPI unavailable; secrets are obfuscated, not encrypted",
            )

    # -- persistence ------------------------------------------------------
    def _read_all(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("secret_store_unreadable", path=str(self.path), error=str(exc))
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    def _write_all(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f"{self.path.name}.tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        with contextlib.suppress(OSError):  # Windows inherits ACLs instead
            os.chmod(temp, 0o600)
        os.replace(temp, self.path)

    # -- api --------------------------------------------------------------
    def set(self, label: str, value: str) -> None:
        data = self._read_all()
        data[label] = protect(value)
        self._write_all(data)

    def get(self, label: str) -> str | None:
        token = self._read_all().get(label)
        if token is None:
            return None
        try:
            return unprotect(token)
        except (OSError, ValueError) as exc:
            logger.error("secret_decrypt_failed", label=label, error=str(exc))
            return None

    def delete(self, label: str) -> None:
        data = self._read_all()
        if data.pop(label, None) is not None:
            self._write_all(data)

    def labels(self) -> list[str]:
        return sorted(self._read_all())

    def has(self, label: str) -> bool:
        return label in self._read_all()


def secret_label_for_model(model_id: str) -> str:
    """Stable secret label for a model configuration."""
    return f"model{SECRET_SEPARATOR}{model_id}"
