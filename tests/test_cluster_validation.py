"""Tests for cluster connection validation and error handling."""

from unittest.mock import MagicMock, patch

import pytest

from kdebug import cli


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global kubectl options before each test."""
    cli.KUBECTL_CONTEXT = None
    cli.KUBECTL_KUBECONFIG = None
    cli.DEBUG_MODE = False
    yield
    cli.KUBECTL_CONTEXT = None
    cli.KUBECTL_KUBECONFIG = None
    cli.DEBUG_MODE = False


class TestValidateClusterConnection:
    """Tests for validate_cluster_connection()."""

    @patch("kdebug.cli.subprocess.run")
    def test_valid_connection_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="namespace/default", stderr=""
        )
        result = cli.validate_cluster_connection("default")
        assert result is None

    @patch("kdebug.cli.subprocess.run")
    def test_invalid_context_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error in configuration: context was not found for specified context: bad",
        )
        result = cli.validate_cluster_connection("default")
        assert result is not None
        assert "context" in result.lower()
        assert "bad" in result

    @patch("kdebug.cli.subprocess.run")
    def test_invalid_kubeconfig_returns_error(self, mock_run):
        cli.KUBECTL_KUBECONFIG = "/bad/path"
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: stat /bad/path: no such file or directory",
        )
        result = cli.validate_cluster_connection("default")
        assert result is not None
        assert "/bad/path" in result

    @patch("kdebug.cli.subprocess.run")
    def test_nonexistent_namespace_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr='Error from server (NotFound): namespaces "nonexistent" not found',
        )
        result = cli.validate_cluster_connection("nonexistent")
        assert result is not None
        assert "nonexistent" in result
        assert "NotFound" in result

    @patch("kdebug.cli.subprocess.run")
    def test_unreachable_cluster_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Unable to connect to the server: dial tcp 10.0.0.1:6443: connect: connection refused",
        )
        result = cli.validate_cluster_connection("default")
        assert result is not None
        assert "Unable to connect" in result

    @patch("kdebug.cli.subprocess.run")
    def test_uses_context_flag(self, mock_run):
        cli.KUBECTL_CONTEXT = "my-context"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cli.validate_cluster_connection("default")
        cmd = mock_run.call_args[0][0]
        assert "--context=my-context" in cmd

    @patch("kdebug.cli.subprocess.run")
    def test_uses_kubeconfig_flag(self, mock_run):
        cli.KUBECTL_KUBECONFIG = "/my/kubeconfig"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cli.validate_cluster_connection("default")
        cmd = mock_run.call_args[0][0]
        assert "--kubeconfig=/my/kubeconfig" in cmd

    @patch("kdebug.cli.subprocess.run")
    def test_includes_namespace_in_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cli.validate_cluster_connection("kube-system")
        cmd = mock_run.call_args[0][0]
        assert "kube-system" in cmd

    @patch("kdebug.cli.subprocess.run")
    def test_strips_stderr_whitespace(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="  some error message  \n",
        )
        result = cli.validate_cluster_connection("default")
        assert result == "some error message"


class TestSelectPodValidation:
    """Tests that select_pod() calls validation and handles errors."""

    def _make_args(self, **kwargs):
        args = MagicMock()
        args.pod = kwargs.get("pod", None)
        args.controller = kwargs.get("controller", None)
        args.namespace = kwargs.get("namespace", None)
        return args

    @patch("kdebug.cli.validate_cluster_connection")
    @patch("kdebug.cli.get_current_namespace", return_value="default")
    def test_returns_none_on_validation_failure(self, mock_ns, mock_validate, capsys):
        mock_validate.return_value = "context was not found for specified context: bad"
        args = self._make_args()
        result = cli.select_pod(args)
        assert result is None
        captured = capsys.readouterr()
        assert "context was not found" in captured.err

    @patch("kdebug.cli.validate_cluster_connection")
    @patch("kdebug.cli.get_current_namespace", return_value="default")
    def test_validation_called_with_explicit_namespace(self, mock_ns, mock_validate):
        mock_validate.return_value = "some error"
        args = self._make_args(namespace="custom-ns")
        cli.select_pod(args)
        mock_validate.assert_called_once_with("custom-ns")

    @patch("kdebug.cli.validate_cluster_connection")
    @patch("kdebug.cli.get_current_namespace", return_value="default")
    def test_validation_called_with_default_namespace(self, mock_ns, mock_validate):
        mock_validate.return_value = "some error"
        args = self._make_args()
        cli.select_pod(args)
        mock_validate.assert_called_once_with("default")

    @patch("kdebug.cli.select_pod_interactive", return_value="my-pod")
    @patch("kdebug.cli.validate_cluster_connection", return_value=None)
    @patch("kdebug.cli.get_current_namespace", return_value="default")
    def test_proceeds_when_validation_passes(
        self, mock_ns, mock_validate, mock_interactive
    ):
        args = self._make_args()
        result = cli.select_pod(args)
        assert result is not None

    @patch("kdebug.cli.get_pod_by_name", return_value=None)
    @patch("kdebug.cli.validate_cluster_connection")
    @patch("kdebug.cli.get_current_namespace", return_value="default")
    def test_skips_validation_when_pod_specified(
        self, mock_ns, mock_validate, mock_get_pod
    ):
        args = self._make_args(pod="my-pod")
        cli.select_pod(args)
        mock_validate.assert_not_called()
        mock_get_pod.assert_called_once_with("my-pod", "default")


class TestKubectlBaseCmd:
    """Tests for kubectl_base_cmd() flag construction."""

    def test_no_flags(self):
        assert cli.kubectl_base_cmd() == "kubectl"

    def test_context_flag(self):
        cli.KUBECTL_CONTEXT = "my-ctx"
        assert cli.kubectl_base_cmd() == "kubectl --context=my-ctx"

    def test_kubeconfig_flag(self):
        cli.KUBECTL_KUBECONFIG = "/path/to/config"
        assert cli.kubectl_base_cmd() == "kubectl --kubeconfig=/path/to/config"

    def test_both_flags(self):
        cli.KUBECTL_KUBECONFIG = "/path/to/config"
        cli.KUBECTL_CONTEXT = "my-ctx"
        result = cli.kubectl_base_cmd()
        assert "--kubeconfig=/path/to/config" in result
        assert "--context=my-ctx" in result
