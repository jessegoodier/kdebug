"""Tests for auto-detecting target container UID."""

import json
from unittest.mock import patch

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


def make_pod_json(
    pod_run_as_user=None,
    containers=None,
):
    """Build a minimal pod JSON for testing."""
    pod = {"spec": {"securityContext": {}, "containers": containers or []}}
    if pod_run_as_user is not None:
        pod["spec"]["securityContext"]["runAsUser"] = pod_run_as_user
    return json.dumps(pod)


class TestGetContainerRunAsUser:
    """Tests for get_container_run_as_user()."""

    @patch("kdebug.cli.run_command")
    def test_container_level_uid(self, mock_run):
        """Container-level runAsUser is returned."""
        mock_run.return_value = make_pod_json(
            containers=[
                {"name": "app", "securityContext": {"runAsUser": 1000}},
            ]
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 1000

    @patch("kdebug.cli.run_command")
    def test_pod_level_uid(self, mock_run):
        """Pod-level runAsUser is returned when no container override."""
        mock_run.return_value = make_pod_json(
            pod_run_as_user=2000,
            containers=[{"name": "app"}],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 2000

    @patch("kdebug.cli.run_command")
    def test_container_overrides_pod(self, mock_run):
        """Container-level runAsUser takes precedence over pod-level."""
        mock_run.return_value = make_pod_json(
            pod_run_as_user=2000,
            containers=[
                {"name": "app", "securityContext": {"runAsUser": 1000}},
            ],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 1000

    @patch("kdebug.cli.run_command")
    def test_neither_set_returns_none(self, mock_run):
        """Returns None when no runAsUser is set anywhere."""
        mock_run.return_value = make_pod_json(
            containers=[{"name": "app"}],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result is None

    @patch("kdebug.cli.run_command")
    def test_multiple_containers_selects_correct(self, mock_run):
        """Selects the correct container when multiple exist."""
        mock_run.return_value = make_pod_json(
            containers=[
                {"name": "sidecar", "securityContext": {"runAsUser": 999}},
                {"name": "app", "securityContext": {"runAsUser": 1000}},
            ],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 1000

    @patch("kdebug.cli.run_command")
    def test_target_container_not_found_falls_back_to_pod(self, mock_run):
        """Falls back to pod-level UID when target container not found."""
        mock_run.return_value = make_pod_json(
            pod_run_as_user=3000,
            containers=[
                {"name": "other", "securityContext": {"runAsUser": 999}},
            ],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 3000

    @patch("kdebug.cli.run_command")
    def test_no_target_container_uses_pod_level(self, mock_run):
        """When target_container is None, uses pod-level UID."""
        mock_run.return_value = make_pod_json(
            pod_run_as_user=5000,
            containers=[
                {"name": "app", "securityContext": {"runAsUser": 1000}},
            ],
        )
        result = cli.get_container_run_as_user("pod1", "default", None)
        assert result == 5000

    @patch("kdebug.cli.run_command")
    def test_empty_output_returns_none(self, mock_run):
        """Returns None when kubectl returns empty output."""
        mock_run.return_value = ""
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result is None

    @patch("kdebug.cli.run_command")
    def test_invalid_json_returns_none(self, mock_run):
        """Returns None when kubectl returns invalid JSON."""
        mock_run.return_value = "not json"
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result is None

    @patch("kdebug.cli.run_command")
    def test_container_without_security_context_falls_back(self, mock_run):
        """Container without securityContext falls back to pod-level."""
        mock_run.return_value = make_pod_json(
            pod_run_as_user=4000,
            containers=[{"name": "app"}],
        )
        result = cli.get_container_run_as_user("pod1", "default", "app")
        assert result == 4000
