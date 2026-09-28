"""Run the root-only backup workflow with fake services/Borg and isolated temp data."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "backup-hill175.sh"


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0, "Linux root integration test (all service/archive commands are mocked)")
class BackupIsolationTest(unittest.TestCase):
    def run_backup(self, fail_create=False):
        with tempfile.TemporaryDirectory(prefix="hill175-backup-test-") as directory:
            root = Path(directory)
            runtime = root / "hill-runtime"
            runtime.mkdir()
            commands = root / "bin"
            commands.mkdir()
            log = root / "commands.jsonl"
            program = f"#!{sys.executable}\n" + r'''
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ["TEST_COMMAND_LOG"], "a") as output:
    output.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == "borg" and sys.argv[1] == "create" and os.environ.get("TEST_FAIL_CREATE") == "1":
    sys.exit(2)
'''
            for name in ("borg", "systemctl"):
                executable = commands / name
                executable.write_text(program, encoding="utf-8")
                executable.chmod(0o700)
            config = root / "credentials.env"
            config.write_text(
                "BORG_REPO_PATH=/unused-test-repository\n"
                "SRV_DIR=/other-minecraft-server\nSERVICE_NAME=other-server.service\n"
                "ARCHIVE_PREFIX=other-server\nKEEP_DAILY=1\n", encoding="utf-8"
            )
            config.chmod(0o600)
            environment = os.environ | {
                "PATH": f"{commands}:{os.environ['PATH']}",
                "HILL175_BACKUP_ENV_FILE": str(config),
                "HILL175_RUNTIME_DIR": str(runtime),
                "HILL175_SERVICE_NAME": "hill175-test.service",
                "HILL175_BACKUP_ARCHIVE_PREFIX": "hill175-test",
                "HILL175_BACKUP_KEEP_DAILY": "14",
                "HILL175_BACKUP_LOCK_WAIT_SECONDS": "1",
                "MC_BACKUP_LOCK": str(root / "backup.lock"),
                "TEST_COMMAND_LOG": str(log),
                "TEST_FAIL_CREATE": "1" if fail_create else "0",
            }
            result = subprocess.run(["bash", str(SCRIPT)], env=environment, capture_output=True, text=True, timeout=15)
            recorded = [json.loads(line) for line in log.read_text().splitlines()]
            return result, recorded, str(runtime)

    def test_shared_credentials_cannot_redirect_runtime_service_or_retention(self):
        result, commands, runtime = self.run_backup()
        self.assertEqual(0, result.returncode, result.stderr)
        create = next(command for command in commands if command[:2] == ["borg", "create"])
        self.assertEqual(runtime, create[-1])
        self.assertIn("::hill175-test-", create[-2])
        prune = next(command for command in commands if command[:2] == ["borg", "prune"])
        self.assertEqual("14", prune[prune.index("--keep-daily") + 1])
        service_commands = [command for command in commands if command[0] == "systemctl"]
        self.assertEqual([
            ["systemctl", "is-active", "--quiet", "hill175-test.service"],
            ["systemctl", "stop", "hill175-test.service"],
            ["systemctl", "start", "hill175-test.service"],
        ], service_commands)

    def test_failed_archive_restarts_only_hill_and_does_not_prune(self):
        result, commands, _ = self.run_backup(fail_create=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(["systemctl", "start", "hill175-test.service"], commands)
        self.assertFalse(any(command[:2] == ["borg", "prune"] for command in commands))


if __name__ == "__main__":
    unittest.main()
