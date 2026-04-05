from __future__ import annotations

import base64
import json
import os
from typing import Any

_DPAPI_PREFIX = "dpapi:"


def dump_secret(payload: dict[str, Any]) -> str:
    """Serialize and protect credential material at rest."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if os.name != "nt":
        raise RuntimeError("Credential encryption requires Windows DPAPI in this runtime")
    protected = _protect_windows(raw)
    token = base64.urlsafe_b64encode(protected).decode("ascii")
    return f"{_DPAPI_PREFIX}{token}"


def load_secret(raw: str) -> dict[str, Any]:
    """Load either protected or legacy plaintext credential payloads."""
    if raw.startswith(_DPAPI_PREFIX):
        if os.name != "nt":
            raise RuntimeError("Credential decryption requires Windows DPAPI in this runtime")
        encoded = raw[len(_DPAPI_PREFIX):].encode("ascii")
        decrypted = _unprotect_windows(base64.urlsafe_b64decode(encoded))
        return json.loads(decrypted.decode("utf-8"))
    return json.loads(raw)


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]


    def _blob_from_bytes(data: bytes):
        buffer = ctypes.create_string_buffer(data, len(data))
        blob = _DataBlob(
            cbData=len(data),
            pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        return blob, buffer


    def _bytes_from_blob(blob: _DataBlob) -> bytes:
        return ctypes.string_at(blob.pbData, blob.cbData)


    def _protect_windows(data: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        source_blob, source_buffer = _blob_from_bytes(data)
        del source_buffer
        target_blob = _DataBlob()
        if not crypt32.CryptProtectData(
            ctypes.byref(source_blob),
            "bsq credentials",
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(target_blob),
        ):
            raise ctypes.WinError()
        try:
            return _bytes_from_blob(target_blob)
        finally:
            kernel32.LocalFree(target_blob.pbData)


    def _unprotect_windows(data: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        source_blob, source_buffer = _blob_from_bytes(data)
        del source_buffer
        target_blob = _DataBlob()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(source_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(target_blob),
        ):
            raise ctypes.WinError()
        try:
            return _bytes_from_blob(target_blob)
        finally:
            kernel32.LocalFree(target_blob.pbData)
