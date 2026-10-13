"""Exercise real Git transitions with isolated repositories and fake system services."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0,
                     "Linux root integration test; all service/install commands are mocked")
class AutoUpdateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hill175-update-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "checkout"
        self.remote = self.root / "origin.git"
        self.author = self.root / "author"
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        self.log = self.root / "installs"
        self.bin.mkdir()
        self.state.mkdir()
        self.env = os.environ | {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "HILL175_UPDATE_STATE_DIR": str(self.state), "TEST_INSTALL_LOG": str(self.log),
        }
        self.git_executable = shutil.which("git")
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.git("init", "-b", "main", str(self.repo), cwd=self.root)
        (self.repo / "ops").mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src/plugin.txt").write_text("original")
        shutil.copyfile(ROOT / "ops/update-server.sh", self.repo / "ops/update-server.sh")
        lock = (ROOT / "ops/deployment-lock.sh").read_text().replace(
            "/run/lock/hill175-deploy.lock", str(self.root / "deploy.lock"))
        (self.repo / "ops/deployment-lock.sh").write_text(lock)
        (self.repo / "ops/check-auth-config.py").write_text(
            'import os, sys\n'
            'if os.environ.get("TEST_BAD_AUTH"): sys.exit(1)\n'
            'print(os.environ.get("TEST_AUTH_MODE", "microsoft"))\n')
        (self.repo / "ops/install-server.sh").write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\n'
            'echo "$1" >> "$TEST_INSTALL_LOG"\n'
            '[[ "${TEST_FAIL_INSTALL:-0}" != 1 ]] || exit 7\n'
            'git rev-parse HEAD > "$HILL175_UPDATE_STATE_DIR/deployed-commit"\n')
        self.git("add", ".")
        self.git("commit", "-m", "Initial source")
        self.initial = self.git("rev-parse", "HEAD").strip()
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-u", "origin", "main")
        self.git("clone", "-b", "main", str(self.remote), str(self.author), cwd=self.root)
        (self.state / "deployed-commit").write_text(self.initial + "\n")
        # Keep Git fetch/pull real and local; stand in only for the displayed origin URL.
        (self.bin / "git").write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$*" == "remote get-url origin" ]]; then\n'
            '  echo "${TEST_ORIGIN:-https://github.com/neilhuang007/Hill-server.git}"\n'
            f'else exec "{self.git_executable}" "$@"; fi\n')
        (self.bin / "systemctl").write_text(
            '#!/usr/bin/env bash\n'
            '[[ "$*" == "is-active --quiet hill175.service" ]] || exit 99\n'
            '[[ "${TEST_SERVICE_STOPPED:-0}" != 1 ]]\n')
        for program in self.bin.iterdir():
            program.chmod(0o700)
        self.env["PATH"] = str(self.bin) + os.pathsep + os.environ["PATH"]

    def git(self, *args, cwd=None):
        return subprocess.check_output([self.git_executable, *args], cwd=cwd or self.repo,
                                       env=self.env, text=True, stderr=subprocess.PIPE)

    def publish(self, path="src/plugin.txt", content="updated"):
        file = self.author / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        self.git("add", ".", cwd=self.author)
        self.git("commit", "-m", "Reviewed update", cwd=self.author)
        self.git("push", "origin", "main", cwd=self.author)
        return self.git("rev-parse", "HEAD", cwd=self.author).strip()

    def run_update(self, action="--apply", **overrides):
        return subprocess.run(["bash", str(self.repo / "ops/update-server.sh"), action],
                              env=self.env | overrides, capture_output=True, text=True, timeout=20)

    def test_new_code_deploys_once_and_preserves_microsoft_mode(self):
        target = self.publish()
        result = self.run_update()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(target, (self.state / "deployed-commit").read_text().strip())
        self.assertFalse((self.state / "failed-commit").exists())
        self.assertEqual(0, self.run_update().returncode)
        self.assertEqual(["--microsoft"], self.log.read_text().splitlines())

    def test_development_mode_remains_explicit(self):
        self.publish()
        self.assertEqual(0, self.run_update(TEST_AUTH_MODE="development").returncode)
        self.assertEqual("--allow-development-auth\n", self.log.read_text())

    def test_check_does_not_pull_or_install(self):
        self.publish()
        self.assertEqual(0, self.run_update("--check").returncode)
        self.assertEqual(self.initial, self.git("rev-parse", "HEAD").strip())
        self.assertFalse(self.log.exists())

    def test_documentation_only_update_pulls_without_restart(self):
        target = self.publish("docs/research/construction.md", "World construction notes")
        self.assertEqual(0, self.run_update().returncode)
        self.assertEqual(target, self.git("rev-parse", "HEAD").strip())
        self.assertEqual(self.initial, (self.state / "deployed-commit").read_text().strip())
        self.assertFalse(self.log.exists())

    def test_dirty_checkout_is_preserved(self):
        self.publish()
        (self.repo / "operator-note.txt").write_text("preserve me")
        self.assertNotEqual(0, self.run_update().returncode)
        self.assertEqual(self.initial, self.git("rev-parse", "HEAD").strip())
        self.assertFalse(self.log.exists())

    def test_diverged_checkout_is_preserved(self):
        self.publish()
        (self.repo / "local.txt").write_text("local commit")
        self.git("add", ".")
        self.git("commit", "-m", "Local work")
        local = self.git("rev-parse", "HEAD")
        self.assertNotEqual(0, self.run_update().returncode)
        self.assertEqual(local, self.git("rev-parse", "HEAD"))
        self.assertFalse(self.log.exists())

    def test_failed_revision_does_not_repeat_or_count_as_deployed(self):
        self.publish()
        self.assertEqual(7, self.run_update(TEST_FAIL_INSTALL="1").returncode)
        self.assertEqual(self.initial, (self.state / "deployed-commit").read_text().strip())
        self.assertNotEqual(0, self.run_update().returncode)
        self.assertEqual(1, len(self.log.read_text().splitlines()))
        self.publish(content="fixed revision")
        self.assertEqual(0, self.run_update().returncode)
        self.assertEqual(2, len(self.log.read_text().splitlines()))

    def test_stopped_server_stays_stopped_and_checkout_is_unchanged(self):
        self.publish()
        self.assertEqual(0, self.run_update(TEST_SERVICE_STOPPED="1").returncode)
        self.assertEqual(self.initial, self.git("rev-parse", "HEAD").strip())
        self.assertFalse(self.log.exists())

    def test_wrong_origin_or_invalid_auth_cannot_install(self):
        self.publish()
        self.assertNotEqual(0, self.run_update(TEST_ORIGIN="https://example.invalid/repo").returncode)
        self.assertNotEqual(0, self.run_update(TEST_BAD_AUTH="1").returncode)
        self.assertFalse(self.log.exists())

    def test_missing_deployment_record_cannot_adopt_checkout(self):
        (self.state / "deployed-commit").unlink()
        self.assertNotEqual(0, self.run_update().returncode)
        self.assertFalse(self.log.exists())

    def test_shared_lock_prevents_overlapping_operations(self):
        import fcntl
        self.publish()
        with (self.root / "deploy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertNotEqual(0, self.run_update().returncode)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
