from __future__ import annotations

import os
import ssl
from typing import Any, Callable, MutableMapping


def _certifi_bundle() -> str:
    import certifi

    return certifi.where()


def ensure_default_ca_bundle(
    *,
    verify_paths: Any | None = None,
    environ: MutableMapping[str, str] | None = None,
    bundle: Callable[[], str] = _certifi_bundle,
) -> None:
    """Point stdlib TLS at certifi when the interpreter has no usable CA bundle.

    The python.org macOS builds ship without a populated ``cert.pem`` until the
    bundled installer command is run, so every stdlib ``urllib`` request fails
    certificate verification. ``requests``-based providers escape this because
    they carry their own certifi store; the RS provider talks stdlib urllib and
    does not. This runs on import, so it must never be the reason an import fails.
    """

    paths = ssl.get_default_verify_paths() if verify_paths is None else verify_paths
    if _exists(getattr(paths, "openssl_cafile", None)) or _exists(getattr(paths, "openssl_capath", None)):
        return
    try:
        resolved = bundle()
    except Exception:  # A repair that cannot run must stay silent, not break the runtime.
        return
    if _exists(resolved):
        target = os.environ if environ is None else environ
        target.setdefault("SSL_CERT_FILE", resolved)


def _exists(path: str | None) -> bool:
    return bool(path) and os.path.exists(path)
