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
    def run_backup(self, fail_create=False, leave_stopped=False, inherit_lock=False):
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
                "HILL175_BACKUP_LEAVE_STOPPED": "true" if leave_stopped else "false",
                "MC_BACKUP_LOCK": str(root / "backup.lock"),
                "TEST_COMMAND_LOG": str(log),
                "TEST_FAIL_CREATE": "1" if fail_create else "0",
            }
            command = ["bash", str(SCRIPT)]
            if inherit_lock:
                command = ["bash", "-c", 'source "$1"; bash "$2"', "test-inherited-lock",
                           str(SCRIPT.with_name("deployment-lock.sh")), str(SCRIPT)]
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
            recorded = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
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

    def test_installer_keeps_old_server_stopped_on_success_and_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                result, commands, _ = self.run_backup(fail_create=fail, leave_stopped=True)
                self.assertEqual(fail, result.returncode != 0, result.stderr)
                self.assertIn(["systemctl", "stop", "hill175-test.service"], commands)
                self.assertNotIn(["systemctl", "start", "hill175-test.service"], commands)

    def test_backup_can_inherit_deployment_lock(self):
        result, _, _ = self.run_backup(leave_stopped=True, inherit_lock=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_separate_backup_cannot_interrupt_deployment(self):
        import fcntl
        with open("/run/lock/hill175-deploy.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result, commands, _ = self.run_backup()
            self.assertNotEqual(0, result.returncode)
            self.assertEqual([], commands)


if __name__ == "__main__":
    unittest.main()
