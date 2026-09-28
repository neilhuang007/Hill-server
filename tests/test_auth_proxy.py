"""Proxy generation must restrict callers, reject stale inputs, and restore failed updates."""

import importlib.util
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "auth_proxy", Path(__file__).resolve().parents[1] / "ops/configure-auth-proxy.py"
)
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class AuthProxyTest(unittest.TestCase):
    def config(self):
        return {
            "HILL175_AUTH_MODE": "microsoft",
            "HILL175_ENTRA_TENANT_ID": "11111111-1111-4111-8111-111111111111",
            "HILL175_ENTRA_CLIENT_ID": "22222222-2222-4222-8222-222222222222",
            "HILL175_ENTRA_CLIENT_SECRET": "test-only-value",
            "HILL175_AUTH_PUBLIC_URL": "https://school.example.org",
            "HILL175_AUTH_PORT": "9087",
        }

    def ranges(self):
        return [ipaddress.ip_network("173.245.48.0/20"), ipaddress.ip_network("2400:cb00::/32")]

    def test_generated_site_restricts_peer_host_tls_and_upstream(self):
        content = proxy.render(self.config(), self.ranges())
        for expected in ["geo $realip_remote_addr", "default 0;", "173.245.48.0/20 1;",
                         "2400:cb00::/32 1;", "ssl_verify_client on;", "server_name school.example.org;",
                         "if ($hill175_cloudflare_peer = 0) { return 444; }",
                         "proxy_pass http://127.0.0.1:9087;", "proxy_set_header Host school.example.org;",
                         "access_log off;", "proxy_cache off;", "/etc/hill175/tls/origin.key"]:
            self.assertIn(expected, content)
        self.assertNotIn("test-only-value", content)
        self.assertNotIn("auth.example.org", content)

    def test_rejects_unsafe_ranges_and_nginx_syntax(self):
        for text, version in [("", 4), ("0.0.0.0/0", 4), ("::/0", 6),
                              ("2400:cb00::/32", 4), ("1.2.3.4/24", 4)]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                proxy.parse_ranges(text, version)
        for value in ["/tmp/key;evil", "/tmp/../key", "relative/key", "/tmp/key name"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                proxy.render(self.config() | {"HILL175_ORIGIN_KEY": value}, self.ranges())
        with self.assertRaises(ValueError):
            proxy.render(self.config() | {"HILL175_AUTH_PUBLIC_URL": "https://host;evil.example.org"}, self.ranges())

    def test_staged_site_rejects_environment_changes_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(proxy, "validate_certificates"):
            staged = Path(directory) / "site.conf"
            content = proxy.render(self.config(), self.ranges())
            staged.write_text(content, encoding="utf-8")
            proxy.validate_prepared(self.config(), staged)
            with self.assertRaises(ValueError):
                proxy.validate_prepared(self.config() | {"HILL175_AUTH_PORT": "9088"}, staged)
            staged.write_text(content.replace("ssl_verify_client on;", "ssl_verify_client off;"), encoding="utf-8")
            with self.assertRaises(ValueError):
                proxy.validate_prepared(self.config(), staged)

    def test_install_preserves_unmanaged_site(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "live.conf"
            target.write_text("manual configuration", encoding="utf-8")
            with self.assertRaises(ValueError):
                proxy.install_site(Path(directory) / "missing-stage", target)
            self.assertEqual("manual configuration", target.read_text())

    def test_failed_nginx_reload_restores_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target, staged = Path(directory) / "live.conf", Path(directory) / "new.conf"
            original = proxy.MARKER + "previous\n"
            target.write_text(original, encoding="utf-8", newline="\n")
            staged.write_text(proxy.MARKER + "replacement\n", encoding="utf-8", newline="\n")
            with patch.object(proxy, "run", side_effect=[b"", RuntimeError("reload failed"), b"", b""]) as run:
                with self.assertRaises(RuntimeError):
                    proxy.install_site(staged, target)
                self.assertEqual(4, run.call_count)
            self.assertEqual(original, target.read_text())

    def test_unchanged_config_reloads_rotated_certificates(self):
        with tempfile.TemporaryDirectory() as directory:
            target, staged = Path(directory) / "live.conf", Path(directory) / "new.conf"
            for path in (target, staged):
                path.write_text(proxy.MARKER + "same\n", encoding="utf-8", newline="\n")
            with patch.object(proxy, "run") as run:
                proxy.install_site(staged, target)
                run.assert_any_call("systemctl", "reload-or-restart", "nginx.service")

    def test_nginx_hostname_conflict_is_fatal_even_with_zero_exit(self):
        result = subprocess.CompletedProcess([], 0, b"", b'[warn] conflicting server name "school.example.org" ignored')
        with patch.object(proxy.subprocess, "run", return_value=result), self.assertRaises(RuntimeError):
            proxy.run("nginx", "-t")

    @unittest.skipUnless(os.name == "posix" and os.geteuid() == 0 and shutil.which("nginx") and shutil.which("openssl"),
                         "Linux root nginx/OpenSSL integration test; no live site is installed")
    def test_real_tls_and_standalone_nginx_validation(self):
        with tempfile.TemporaryDirectory(prefix="hill175-proxy-test-") as directory:
            root = Path(directory)
            cert, key = root / "origin.pem", root / "origin.key"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                            "-keyout", str(key), "-out", str(cert), "-subj", "/CN=school.example.org",
                            "-addext", "subjectAltName=DNS:school.example.org"],
                           check=True, capture_output=True, timeout=30)
            key.chmod(0o600)
            values = self.config() | {"HILL175_ORIGIN_CERT": str(cert), "HILL175_ORIGIN_KEY": str(key),
                                      "HILL175_AOP_CA": str(cert)}
            with patch.object(proxy, "TARGET", root / "unused-live-site"), patch.object(proxy, "cloudflare_ranges", return_value=self.ranges()):
                staged = proxy.prepare(values, root / "stage")
                proxy.validate_prepared(values, staged)
            with self.assertRaises(ValueError):
                proxy.validate_certificates(values | {"HILL175_AUTH_PUBLIC_URL": "https://wrong.example.org"})


if __name__ == "__main__":
    unittest.main()
