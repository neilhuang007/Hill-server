"""Deployment preflight must reject ambiguous modes and unsafe credential syntax."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "auth_config", Path(__file__).resolve().parents[1] / "ops" / "check-auth-config.py"
)
auth_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auth_config)


class AuthEnvironmentTest(unittest.TestCase):
    def config(self):
        return {
            "HILL175_AUTH_MODE": "microsoft",
            "HILL175_ENTRA_TENANT_ID": "11111111-1111-4111-8111-111111111111",
            "HILL175_ENTRA_CLIENT_ID": "22222222-2222-4222-8222-222222222222",
            "HILL175_ENTRA_CLIENT_SECRET": "test-only-value",
            "HILL175_AUTH_PUBLIC_URL": "https://auth.example.org",
        }

    def test_valid_modes_and_defaults(self):
        self.assertEqual(("microsoft", 8087), auth_config.validate(self.config()))
        self.assertEqual(("development", 8087), auth_config.validate({"HILL175_AUTH_MODE": "development"}))

    def test_explicit_bedrock_enable_is_honored_in_development(self):
        for values, expected in [({'HILL175_AUTH_MODE': 'development'}, 'false'),
                                 ({'HILL175_AUTH_MODE': 'development', 'HILL175_BEDROCK_ENABLED': 'true'}, 'true')]:
            output = StringIO()
            with patch('sys.argv', ['check-auth-config.py', '--print', 'bedrock-enabled']), \
                    patch.object(auth_config, 'read_environment', return_value=values), redirect_stdout(output):
                self.assertEqual(0, auth_config.main())
            self.assertEqual(expected, output.getvalue().strip())

    def test_cannot_silently_change_modes(self):
        for values, mode in [({}, None), (self.config(), "development"), ({"HILL175_AUTH_MODE": "stub"}, None)]:
            with self.subTest(values=tuple(values), mode=mode), self.assertRaises(ValueError):
                auth_config.validate(values, mode)

    def test_rejects_invalid_required_values(self):
        invalid = {
            "HILL175_ENTRA_TENANT_ID": ["", "00000000-0000-0000-0000-000000000000"],
            "HILL175_ENTRA_CLIENT_SECRET": ["", "replace-with-secret"],
            "HILL175_AUTH_PUBLIC_URL": ["http://auth.example.org", "https://user:secret@auth.example.org", "https://auth.example.org/redirect", "https://auth.example.org?query=1", "https://auth.example.org:8443"],
            "HILL175_AUTH_PORT": ["0", "65536", "bad"],
            "HILL175_MAX_LINKED_ACCOUNTS": ["1", "21"],
            "HILL175_BEDROCK_ENABLED": ["yes", "1", "TRUE"],
            "HILL175_BEDROCK_PORT": ["0", "65535", "65536", "bad"],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    auth_config.validate(self.config() | {key: value})

    def test_reads_literals_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hill175.env"
            path.write_text("# comment\nHILL175_AUTH_MODE=microsoft\nHILL175_ENTRA_CLIENT_SECRET='$(never-execute);$literal#value'\n", encoding="utf-8")
            values = auth_config.read_environment(path, check_permissions=False)
            self.assertEqual("$(never-execute);$literal#value", values["HILL175_ENTRA_CLIENT_SECRET"])

    def test_rejects_ambiguous_systemd_syntax(self):
        for content in ["export HILL175_AUTH_MODE=microsoft", "HILL175_AUTH_MODE=microsoft\nHILL175_AUTH_MODE=development", "UNKNOWN_KEY=value", "HILL175_AUTH_MODE=microsoft # comment", "HILL175_ENTRA_CLIENT_SECRET='multi\nline'"]:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "hill175.env"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    auth_config.read_environment(path, check_permissions=False)


if __name__ == "__main__":
    unittest.main()
