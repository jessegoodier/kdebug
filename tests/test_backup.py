"""Tests for create_backup() tar command construction."""

from unittest.mock import patch

import pytest

from kdebug import cli


@pytest.fixture(autouse=True)
def reset_globals():
    cli.KUBECTL_CONTEXT = None
    cli.KUBECTL_KUBECONFIG = None
    cli.DEBUG_MODE = False
    yield
    cli.KUBECTL_CONTEXT = None
    cli.KUBECTL_KUBECONFIG = None
    cli.DEBUG_MODE = False


# run_command call order for compress=True:
#   0 - path verify (ls -d)       must return non-empty to pass
#   1 - tar exec
#   2 - kubectl cp
#   3 - rm cleanup
_COMPRESS_SIDE_EFFECTS = ["/proc/1/root/var/configs", "", "", ""]


def _call_cmd(mock_run, index):
    """Return the command string from the Nth run_command call."""
    return mock_run.call_args_list[index][0][0]


@patch("os.makedirs")
@patch("kdebug.cli.run_command")
class TestCreateBackupTarCommand:
    """Verify tar command construction inside create_backup()."""

    def test_no_excludes(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup("pod1", "default", "dbg", "/var/configs", "./out", compress=True)
        tar_cmd = _call_cmd(mock_run, 1)
        assert "tar czf" in tar_cmd
        assert "--exclude" not in tar_cmd
        assert "/proc/1/root/var/configs" in tar_cmd

    def test_single_exclude(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out",
            compress=True, tar_excludes=["waterfowl"],
        )
        tar_cmd = _call_cmd(mock_run, 1)
        assert "--exclude=waterfowl" in tar_cmd

    def test_multiple_excludes(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out",
            compress=True, tar_excludes=["waterfowl", "tmp", "*.log"],
        )
        tar_cmd = _call_cmd(mock_run, 1)
        assert "--exclude=waterfowl" in tar_cmd
        assert "--exclude=tmp" in tar_cmd
        assert "--exclude=*.log" in tar_cmd

    def test_leading_slash_stripped_from_exclude(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out",
            compress=True, tar_excludes=["/var/configs/waterfowl"],
        )
        tar_cmd = _call_cmd(mock_run, 1)
        assert "--exclude=var/configs/waterfowl" in tar_cmd
        assert "--exclude=/var/configs/waterfowl" not in tar_cmd

    def test_container_path_leading_slash_stripped(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out", compress=True
        )
        tar_cmd = _call_cmd(mock_run, 1)
        assert "/proc/1/root/var/configs" in tar_cmd
        assert "/proc/1/root//var/configs" not in tar_cmd

    def test_compress_appends_tar_gz_suffix(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs",
            "./backups/{namespace}/{pod}", compress=True,
        )
        cp_cmd = _call_cmd(mock_run, 2)
        assert ".tar.gz" in cp_cmd

    def test_cleanup_runs_after_compress(self, mock_run, mock_makedirs):
        mock_run.side_effect = _COMPRESS_SIDE_EFFECTS.copy()
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out", compress=True
        )
        assert mock_run.call_count == 4  # verify + tar + cp + rm
        cleanup_cmd = _call_cmd(mock_run, 3)
        assert "rm -f /tmp/kdebug-backup.tar.gz" in cleanup_cmd

    def test_compress_false_uses_kubectl_cp_directly(self, mock_run, mock_makedirs):
        # compress=False: verify + kubectl cp (no tar, no cleanup)
        mock_run.side_effect = ["/proc/1/root/var/configs", ""]
        cli.create_backup(
            "pod1", "default", "dbg", "/var/configs", "./out", compress=False
        )
        assert mock_run.call_count == 2
        cp_cmd = _call_cmd(mock_run, 1)
        assert "tar" not in cp_cmd
        assert "kubectl cp" in cp_cmd
