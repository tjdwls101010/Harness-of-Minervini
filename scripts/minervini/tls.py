from __future__ import annotations

import os
import ssl
from typing import Any, MutableMapping


def ensure_default_ca_bundle(
    *,
    verify_paths: Any | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Point stdlib TLS at certifi when the interpreter has no usable CA bundle.

    The python.org macOS builds ship without a populated ``cert.pem`` until the
    bundled installer command is run, so every stdlib ``urllib`` request fails
    certificate verification. ``requests``-based providers escape this because
    they carry their own certifi store; the RS provider talks stdlib urllib and
    does not.
    """

    import certifi

    paths = ssl.get_default_verify_paths() if verify_paths is None else verify_paths
    if _exists(getattr(paths, "openssl_cafile", None)) or _exists(getattr(paths, "openssl_capath", None)):
        return
    target = os.environ if environ is None else environ
    target.setdefault("SSL_CERT_FILE", certifi.where())


def _exists(path: str | None) -> bool:
    return bool(path) and os.path.exists(path)
