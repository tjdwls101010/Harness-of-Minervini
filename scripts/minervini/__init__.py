"""Harness of Minervini v2 runtime."""

from .tls import ensure_default_ca_bundle

SCHEMA_VERSION = "2.0.0"

ensure_default_ca_bundle()
