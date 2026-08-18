from __future__ import annotations

from dataclasses import dataclass
import subprocess
import sys
import tempfile
import unittest

from scripts.minervini.tls import ensure_default_ca_bundle


@dataclass(frozen=True)
class FakeVerifyPaths:
    """The two fields of ssl.get_default_verify_paths() this module reads."""

    openssl_cafile: str | None
    openssl_capath: str | None


class DefaultCaBundleTests(unittest.TestCase):
    def test_missing_interpreter_ca_bundle_points_stdlib_tls_at_certifi(self) -> None:
        import certifi

        environ: dict[str, str] = {}

        ensure_default_ca_bundle(
            verify_paths=FakeVerifyPaths("/nonexistent/etc/openssl/cert.pem", "/nonexistent/etc/openssl/certs"),
            environ=environ,
        )

        self.assertEqual(environ["SSL_CERT_FILE"], certifi.where())

    def test_an_operator_supplied_bundle_is_never_overwritten(self) -> None:
        environ = {"SSL_CERT_FILE": "/operator/chosen/roots.pem"}

        ensure_default_ca_bundle(
            verify_paths=FakeVerifyPaths("/nonexistent/etc/openssl/cert.pem", "/nonexistent/etc/openssl/certs"),
            environ=environ,
        )

        self.assertEqual(environ["SSL_CERT_FILE"], "/operator/chosen/roots.pem")

    def test_a_working_interpreter_bundle_is_left_alone(self) -> None:
        environ: dict[str, str] = {}

        with tempfile.NamedTemporaryFile(suffix=".pem") as bundle:
            ensure_default_ca_bundle(
                verify_paths=FakeVerifyPaths(bundle.name, "/nonexistent/etc/openssl/certs"),
                environ=environ,
            )

        self.assertEqual(environ, {})

    def test_an_unavailable_certifi_never_breaks_importing_the_runtime(self) -> None:
        def missing_bundle() -> str:
            raise ModuleNotFoundError("No module named 'certifi'")

        environ: dict[str, str] = {}

        ensure_default_ca_bundle(
            verify_paths=FakeVerifyPaths("/nonexistent/etc/openssl/cert.pem", None),
            environ=environ,
            bundle=missing_bundle,
        )

        self.assertEqual(environ, {})


class RuntimeImportTests(unittest.TestCase):
    def test_importing_the_runtime_leaves_stdlib_tls_able_to_verify(self) -> None:
        probe = (
            "import scripts.minervini, ssl;"
            "print(ssl.create_default_context().cert_store_stats()['x509_ca'])"
        )

        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "."},
        )

        self.assertGreater(int(completed.stdout.strip()), 0)


if __name__ == "__main__":
    unittest.main()
