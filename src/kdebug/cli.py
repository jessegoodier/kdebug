#!/usr/bin/env python3

"""
kdebug.py - Universal Kubernetes Debug Container Utility

A utility for launching ephemeral debug containers in Kubernetes pods with
interactive shell access and backup capabilities.

Usage Examples:
    # Interactive debug session (default subcommand)
    kdebug -n kubecost --controller sts/aggregator --container aggregator --cmd bash
    kdebug debug -n kubecost --pod aggregator-0 --container aggregator

    # Backup mode
    kdebug backup -n kubecost --pod aggregator-0 --container aggregator --container-path /var/configs
    kdebug backup --pod web-0 --container-path /var/data --local-path ./my-backups/{namespace}/{pod}
"""

import argparse
import importlib.resources
import json
import os
import re
import subprocess
import sys
import termios
import time
import tty
from typing import Dict, List, Optional, Tuple

import rich.box as box
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from kdebug import __version__

# Global debug flag
DEBUG_MODE = False

# Global kubectl options (set after argument parsing)
KUBECTL_CONTEXT = None
KUBECTL_KUBECONFIG = None

_KDEBUG_THEME = Theme(
    {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "cyan",
        "pod": "cyan",
        "container": "cyan",
        "namespace": "magenta",
        "controller": "yellow",
        "border": "blue",
        "dim": "dim white",
        "config_src": "dim white",
        "highlight": "bold bright_green",
        "menu_title": "bold bright_cyan",
    }
)
console = Console(theme=_KDEBUG_THEME, highlight=False)
err_console = Console(stderr=True, theme=_KDEBUG_THEME, highlight=False)

# Controller type aliases
CONTROLLER_ALIASES = {
    "deployment": "Deployment",
    "deploy": "Deployment",
    "statefulset": "StatefulSet",
    "sts": "StatefulSet",
    "daemonset": "DaemonSet",
    "ds": "DaemonSet",
}


def kubectl_base_cmd() -> str:
    """Return kubectl command with global options."""
    parts = ["kubectl"]
    if KUBECTL_KUBECONFIG:
        parts.append(f"--kubeconfig={KUBECTL_KUBECONFIG}")
    if KUBECTL_CONTEXT:
        parts.append(f"--context={KUBECTL_CONTEXT}")
    return " ".join(parts)


def print_debug_command(cmd: str):
    """Print command in a nice format when debug mode is enabled."""
    if DEBUG_MODE:
        console.rule("[dim]DEBUG: Executing command[/]", style="dim")
        console.print(f"  [dim]{escape(cmd)}[/]")
        console.rule(style="dim")


def run_command(cmd: str, check: bool = True, use_bash: bool = False) -> Optional[str]:
    """Run a shell command and return the output."""
    print_debug_command(cmd)
    try:
        if use_bash:
            # Use bash explicitly for commands that need bash features like process substitution
            result = subprocess.run(
                ["bash", "-c", cmd], capture_output=True, text=True, check=check
            )
        else:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, check=check
            )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        err_console.print(f"[error]Error running command:[/] {escape(cmd)}")
        err_console.print(f"[error]Error:[/] {escape(e.stderr)}")
        if check:
            return None
        raise


def get_current_namespace() -> str:
    """Get the current namespace from kubectl context."""
    cmd = (
        f"{kubectl_base_cmd()} config view --minify --output 'jsonpath={{..namespace}}'"
    )
    output = run_command(cmd, check=False)
    return output if output else "default"


_CONFIG_KEYS = {"debugImage", "cmd", "cdInto", "backupContainerPath", "backupLocalPath"}

_HARDCODED_DEFAULTS = {
    "debugImage": "ghcr.io/jessegoodier/toolbox-common:latest",
    "cmd": "bash",
}


def load_config() -> Dict:
    """Load config from ~/.config/kdebug/kdebug.json (respects XDG_CONFIG_HOME).

    Returns a dict of config values, or empty dict if no config file exists.
    """
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    config_path = os.path.join(config_home, "kdebug", "kdebug.json")

    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        err_console.print(
            f"[warning]⚠ Warning:[/] Failed to parse {escape(config_path)}: {escape(str(e))}"
        )
        return {}

    unknown_keys = set(config.keys()) - _CONFIG_KEYS
    if unknown_keys:
        err_console.print(
            f"[warning]⚠ Warning:[/] Unknown config keys in {escape(config_path)}: {', '.join(sorted(unknown_keys))}"
        )

    # Expand ${VAR} environment variables in string values
    def expand_env(value):
        if isinstance(value, str):
            return re.sub(
                r"\$\{(\w+)\}",
                lambda m: os.environ.get(m.group(1), m.group(0)),
                value,
            )
        return value

    return {k: expand_env(v) for k, v in config.items() if k in _CONFIG_KEYS}


def validate_cluster_connection(namespace: str) -> Optional[str]:
    """Validate kubectl can connect to the cluster and namespace exists.

    Returns None on success, or an error message string on failure.
    """
    cmd = f"{kubectl_base_cmd()} get pods -n {namespace} --limit=1 -o name"
    print_debug_command(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip()
    return None


def get_pod_by_name(pod_name: str, namespace: str) -> Optional[Dict]:
    """Get pod information by name."""
    console.print(
        f"Looking up pod [pod]{escape(pod_name)}[/] in namespace [namespace]{escape(namespace)}[/]..."
    )

    cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        err_console.print(
            f"[error]✗ Error:[/] Pod '{escape(pod_name)}' not found in namespace '{escape(namespace)}'"
        )
        return None

    try:
        pod_data = json.loads(output)
        return {
            "name": pod_data.get("metadata", {}).get("name", ""),
            "namespace": namespace,
        }
    except json.JSONDecodeError as e:
        err_console.print(f"[error]Error parsing pod JSON:[/] {escape(str(e))}")
        return None


def get_pods_by_controller(
    controller_type: str, controller_name: str, namespace: str
) -> List[Dict]:
    """Get all pods owned by a specific controller using owner references."""
    # Normalize controller type
    controller_kind = CONTROLLER_ALIASES.get(controller_type.lower())
    if not controller_kind:
        err_console.print(
            f"[error]Error:[/] Unknown controller type '{escape(controller_type)}'"
        )
        err_console.print(f"Supported types: {', '.join(CONTROLLER_ALIASES.keys())}")
        return []

    console.print(
        f"Searching for pods from [controller]{escape(controller_kind)}[/] [pod]{escape(controller_name)}[/] in namespace [namespace]{escape(namespace)}[/]..."
    )

    # Get all pods in the namespace
    cmd = f"{kubectl_base_cmd()} get pods -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        err_console.print("[error]Error:[/] Failed to get pods")
        return []

    try:
        pods_data = json.loads(output)
    except json.JSONDecodeError as e:
        err_console.print(f"[error]Error parsing pods JSON:[/] {escape(str(e))}")
        return []

    matching_pods = []

    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        owner_refs = pod.get("metadata", {}).get("ownerReferences", [])
        pod_matched = False

        # Check direct ownership (works for StatefulSet, DaemonSet)
        for ref in owner_refs:
            if (
                ref.get("kind") == controller_kind
                and ref.get("name") == controller_name
            ):
                matching_pods.append({"name": pod_name, "namespace": namespace})
                pod_matched = True
                break

        # For Deployments, check if owned by a ReplicaSet that belongs to our Deployment
        if controller_kind == "Deployment" and not pod_matched:
            for ref in owner_refs:
                if ref.get("kind") == "ReplicaSet":
                    rs_name = ref.get("name", "")
                    # ReplicaSet names typically start with deployment name
                    if rs_name.startswith(controller_name + "-"):
                        matching_pods.append({"name": pod_name, "namespace": namespace})
                        pod_matched = True
                        break

    return matching_pods


def get_all_controllers(namespace: str) -> Dict[str, List[Dict]]:
    """Get all controllers (deployments, statefulsets, daemonsets) in namespace."""
    controllers = {"Deployment": [], "StatefulSet": [], "DaemonSet": []}

    for controller_type in ["deployment", "statefulset", "daemonset"]:
        cmd = f"{kubectl_base_cmd()} get {controller_type} -n {namespace} -o json"
        output = run_command(cmd, check=False)

        if output:
            try:
                data = json.loads(output)
                for item in data.get("items", []):
                    name = item.get("metadata", {}).get("name", "")
                    replicas = item.get("spec", {}).get("replicas", 0)
                    ready = item.get("status", {}).get("readyReplicas", 0)

                    controller_kind = CONTROLLER_ALIASES.get(
                        controller_type, controller_type
                    )
                    controllers[controller_kind].append(
                        {
                            "name": name,
                            "type": controller_type,
                            "kind": controller_kind,
                            "replicas": replicas,
                            "ready": ready,
                        }
                    )
            except json.JSONDecodeError:
                pass

    return controllers


def get_all_pods(namespace: str) -> List[Dict]:
    """Get all pods in namespace with their status."""
    cmd = f"{kubectl_base_cmd()} get pods -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        return []

    try:
        data = json.loads(output)
        pods = []
        for item in data.get("items", []):
            name = item.get("metadata", {}).get("name", "")
            status = item.get("status", {}).get("phase", "Unknown")
            pods.append({"name": name, "status": status, "namespace": namespace})
        return pods
    except json.JSONDecodeError:
        return []


def read_key() -> str:
    """Read a single keypress from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Handle arrow keys (escape sequences)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "up"
                elif ch3 == "B":
                    return "down"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _build_menu_renderable(
    title: str, items: List[str], selected_idx: int, show_numbers: bool = True
) -> Panel:
    """Build a rich Panel renderable for the interactive menu."""
    content = Text()
    for idx, item in enumerate(items):
        number = f"{idx + 1}. " if show_numbers else ""
        if idx == selected_idx:
            content.append(f"▶ {number}", style="highlight")
            content.append_text(Text.from_markup(item + "\n", style="highlight"))
        else:
            content.append(f"  {number}", style="white")
            content.append_text(Text.from_markup(item + "\n"))
    quit_idx = len(items)
    if selected_idx == quit_idx:
        content.append("\n▶ q. Quit\n", style="highlight")
    else:
        content.append("\n  q. Quit\n", style="white")
    instructions = (
        "Use ↑/↓ arrows or numbers to select, Enter to confirm"
        if show_numbers
        else "Use ↑/↓ arrows to select, Enter to confirm"
    )
    content.append(f"\n{instructions}", style="config_src")
    return Panel(
        content,
        title=Text.from_markup(f"[menu_title]{title}[/]"),
        title_align="left",
        border_style="border",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def interactive_menu(
    title: str, items: List[str], show_numbers: bool = True
) -> Optional[int]:
    """Display an interactive menu and return the selected index."""
    if not items:
        err_console.print("[error]✗ Error:[/] No items to display")
        return None

    selected_idx = 0
    quit_idx = len(items)

    with Live(
        _build_menu_renderable(title, items, selected_idx, show_numbers),
        console=console,
        auto_refresh=False,
        transient=True,
    ) as live:
        while True:
            key = read_key()
            if key == "up":
                selected_idx = (selected_idx - 1) % (quit_idx + 1)
            elif key == "down":
                selected_idx = (selected_idx + 1) % (quit_idx + 1)
            elif key in ("\r", "\n"):
                return None if selected_idx == quit_idx else selected_idx
            elif key in ("q", "Q"):
                return None
            elif key.isdigit() and show_numbers:
                num = int(key)
                if 1 <= num <= len(items):
                    return num - 1
            live.update(
                _build_menu_renderable(title, items, selected_idx, show_numbers),
                refresh=True,
            )


def select_controller_interactive(namespace: str) -> Optional[Tuple[str, str]]:
    """Interactive TUI for selecting a controller."""
    with console.status("[warning]Fetching controllers...[/]", spinner="dots"):
        controllers = get_all_controllers(namespace)

    # Flatten controllers into menu items
    menu_items = []
    controller_map = []

    for kind in ["Deployment", "StatefulSet", "DaemonSet"]:
        for ctrl in controllers[kind]:
            ready_style = "success" if ctrl["ready"] == ctrl["replicas"] else "warning"
            menu_items.append(
                f"[controller]{escape(kind)}[/] [pod]{escape(ctrl['name'])}[/] "
                f"([{ready_style}]{ctrl['ready']}/{ctrl['replicas']}[/])"
            )
            controller_map.append((ctrl["type"], ctrl["name"]))

    if not menu_items:
        err_console.print(
            f"[error]✗ Error:[/] No controllers found in namespace [namespace]{escape(namespace)}[/]"
        )
        return None

    title = f"Select Controller in namespace: [namespace]{escape(namespace)}[/]"
    selected_idx = interactive_menu(title, menu_items)

    if selected_idx is None:
        return None

    return controller_map[selected_idx]


def select_pod_interactive(namespace: str) -> Optional[str]:
    """Interactive TUI for selecting a pod."""
    with console.status("[warning]Fetching pods...[/]", spinner="dots"):
        pods = get_all_pods(namespace)

    if not pods:
        err_console.print(
            f"[error]✗ Error:[/] No pods found in namespace [namespace]{escape(namespace)}[/]"
        )
        return None

    # Create menu items
    menu_items = []
    for pod in pods:
        status_style = "success" if pod["status"] == "Running" else "warning"
        menu_items.append(
            f"[pod]{escape(pod['name'])}[/] ([{status_style}]{escape(pod['status'])}[/])"
        )

    title = f"Select Pod in namespace: [namespace]{escape(namespace)}[/]"
    selected_idx = interactive_menu(title, menu_items)

    if selected_idx is None:
        return None

    return pods[selected_idx]["name"]


def select_pod(args) -> Optional[Dict]:
    """Select a pod based on provided arguments."""
    namespace = args.namespace or get_current_namespace()

    # Validate cluster connection and namespace before proceeding
    error = validate_cluster_connection(namespace)
    if error:
        err_console.print(f"[error]✗ Error:[/] {escape(error)}")
        return None

    # Direct pod selection
    if args.pod:
        return get_pod_by_name(args.pod, namespace)

    # Controller-based selection
    if args.controller:
        controller_type, controller_name = args.controller
        pods = get_pods_by_controller(controller_type, controller_name, namespace)

        if not pods:
            err_console.print(
                f"[error]No pods found for {escape(controller_type)} '{escape(controller_name)}'[/]"
            )
            return None

        if len(pods) > 1:
            console.print(
                f"Found [warning]{len(pods)}[/] pods, selecting first one: [pod]{escape(pods[0]['name'])}[/]"
            )

        return pods[0]

    # Interactive mode - no pod or controller specified
    console.print("\n[info]Starting interactive pod selection...[/]")

    # Direct pod selection via TUI
    pod_name = select_pod_interactive(namespace)
    if not pod_name:
        console.print("\n[info]Selection cancelled[/]")
        return None

    return {"name": pod_name, "namespace": namespace}


def get_pod_containers(pod_name: str, namespace: str) -> Dict[str, List[str]]:
    """Get all containers from a pod, separated by type."""
    cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
    output = run_command(cmd)

    if not output:
        return {"containers": [], "init_containers": [], "ephemeral_containers": []}

    try:
        pod_data = json.loads(output)
    except json.JSONDecodeError as e:
        err_console.print(f"[error]Error parsing pod JSON:[/] {escape(str(e))}")
        return {"containers": [], "init_containers": [], "ephemeral_containers": []}

    spec = pod_data.get("spec", {})

    containers = [
        container.get("name")
        for container in spec.get("containers", [])
        if container.get("name")
    ]

    init_containers = [
        container.get("name")
        for container in spec.get("initContainers", [])
        if container.get("name")
    ]

    ephemeral_containers = [
        container.get("name")
        for container in spec.get("ephemeralContainers", [])
        if container.get("name")
    ]

    return {
        "containers": containers,
        "init_containers": init_containers,
        "ephemeral_containers": ephemeral_containers,
    }


def get_existing_ephemeral_containers(pod_name: str, namespace: str) -> List[str]:
    """Get list of existing ephemeral container names."""
    container_info = get_pod_containers(pod_name, namespace)
    return container_info["ephemeral_containers"]


def wait_for_container_running(
    pod_name: str, namespace: str, container_name: str, timeout: int = 120
) -> bool:
    """Poll until the container is in running state or timeout."""
    # Known failure states that should immediately fail
    failure_states = {
        "ImagePullBackOff",
        "ErrImagePull",
        "CrashLoopBackOff",
        "CreateContainerError",
        "InvalidImageName",
        "CreateContainerConfigError",
    }

    start_time = time.time()
    last_reason = None
    result_success = False
    failure_reason = None
    failure_message = None
    is_terminated = False
    exit_code_val = None

    with console.status(
        f"Waiting for [pod]{escape(container_name)}[/] to start...", spinner="dots"
    ) as status:
        while time.time() - start_time < timeout:
            output = run_command(
                f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
            )
            if not output:
                time.sleep(2)
                continue

            try:
                pod_data = json.loads(output)
                for s in pod_data.get("status", {}).get(
                    "ephemeralContainerStatuses", []
                ):
                    if s.get("name") != container_name:
                        continue
                    state = s.get("state", {})

                    if "running" in state:
                        result_success = True
                        break
                    elif "waiting" in state:
                        r = state["waiting"].get("reason", "Unknown")
                        if r in failure_states:
                            failure_reason = r
                            failure_message = state["waiting"].get("message", "")
                            break
                        if r != last_reason:
                            status.update(
                                f"Container [pod]{escape(container_name)}[/]: [warning]{escape(r)}[/]"
                            )
                            last_reason = r
                    elif "terminated" in state:
                        t = state["terminated"]
                        failure_reason = t.get("reason", "Unknown")
                        failure_message = t.get("message", "")
                        is_terminated = True
                        exit_code_val = t.get("exitCode", "N/A")
                        break
                    elif last_reason != "NoState":
                        status.update(
                            f"Container [pod]{escape(container_name)}[/]: Initializing..."
                        )
                        last_reason = "NoState"

            except json.JSONDecodeError as e:
                err_console.print(
                    f"[warning]Warning:[/] Failed to parse pod JSON: {escape(str(e))}"
                )

            if result_success or failure_reason:
                break
            time.sleep(2)

    if result_success:
        console.print(
            f"[success]✓[/] Container [pod]{escape(container_name)}[/] is [success]running[/]"
        )
        return True
    if failure_reason:
        if is_terminated:
            err_console.print(
                f"[error]✗[/] Container terminated: [error]{escape(failure_reason)}[/] "
                f"(exit code: [error]{exit_code_val}[/])"
            )
        else:
            err_console.print(
                f"[error]✗[/] Container failed to start: [error]{escape(failure_reason)}[/]"
            )
        if failure_message:
            err_console.print(f"[error]Error details:[/] {escape(failure_message)}")
        return False
    err_console.print(
        f"[error]✗[/] Timeout ({timeout}s) waiting for container to start"
    )
    if last_reason:
        err_console.print(f"Last known status: [warning]{escape(last_reason)}[/]")
    return False


def check_pod_security_context(pod_name: str, namespace: str) -> Dict:
    """Check the pod's security context to see if running as root is allowed."""
    cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        return {"can_run_as_root": True, "reason": "Unable to check"}

    try:
        pod_data = json.loads(output)
        spec = pod_data.get("spec", {})

        # Check pod-level security context
        pod_security_context = spec.get("securityContext", {})
        run_as_non_root = pod_security_context.get("runAsNonRoot", False)

        # Check container-level security contexts
        containers = spec.get("containers", [])
        for container in containers:
            container_security = container.get("securityContext", {})
            container_run_as_non_root = container_security.get("runAsNonRoot", False)

            if container_run_as_non_root or run_as_non_root:
                return {
                    "can_run_as_root": False,
                    "reason": "Pod has runAsNonRoot policy enabled",
                }

        return {"can_run_as_root": True, "reason": "No restrictions found"}

    except json.JSONDecodeError:
        return {"can_run_as_root": True, "reason": "Unable to parse pod spec"}


def get_container_run_as_user(
    pod_name: str, namespace: str, target_container: Optional[str]
) -> Optional[int]:
    """Detect the runAsUser UID from the target container or pod security context."""
    cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        return None

    try:
        pod_data = json.loads(output)
        spec = pod_data.get("spec", {})

        # Check container-level securityContext first (overrides pod-level)
        if target_container:
            for container in spec.get("containers", []):
                if container.get("name") == target_container:
                    container_uid = container.get("securityContext", {}).get(
                        "runAsUser"
                    )
                    if container_uid is not None:
                        return int(container_uid)
                    break

        # Fall back to pod-level securityContext
        pod_uid = spec.get("securityContext", {}).get("runAsUser")
        if pod_uid is not None:
            return int(pod_uid)

    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    return None


def launch_debug_container(
    pod_name: str,
    namespace: str,
    debug_image: str,
    target_container: Optional[str],
    existing_containers: List[str],
    as_root: bool = False,
    run_as_user: Optional[int] = None,
) -> Optional[str]:
    """Launch a debug container attached to the pod and return its name."""
    console.print(f"Launching debug container for pod [pod]{escape(pod_name)}[/]...")

    # Check if running as root is possible when requested
    if as_root:
        security_check = check_pod_security_context(pod_name, namespace)
        if not security_check["can_run_as_root"]:
            err_console.print(
                f"[warning]⚠ Warning:[/] {escape(security_check['reason'])}"
            )
            err_console.print(
                "[warning]The --as-root flag will likely fail.[/] Proceeding anyway..."
            )
            console.print("[info]Tip:[/] Try without --as-root flag\n")
    elif run_as_user is not None:
        console.print(
            f"Running as UID [pod]{run_as_user}[/] (matching target container)"
        )

    # Build kubectl debug command
    cmd_parts = [
        f"nohup {kubectl_base_cmd()} debug -i --tty",
        pod_name,
        f"--namespace={namespace}",
    ]

    if target_container:
        cmd_parts.append(f"--target={target_container}")

    cmd_parts.extend(
        [
            "--share-processes",
            "--profile=general",
        ]
    )

    if as_root:
        cmd_parts.append('--custom=<(echo \'{"securityContext":{"runAsUser":0}}\')')
    elif run_as_user is not None:
        cmd_parts.append(
            f'--custom=<(echo \'{{"securityContext":{{"runAsUser":{run_as_user}}}}}\')'
        )

    cmd_parts.extend(
        [
            f"--image={debug_image}",
            "-- sleep 1440 > /dev/null 2>&1 &",
        ]
    )

    cmd = " ".join(cmd_parts)
    run_command(cmd, check=False, use_bash=True)

    # Give kubectl a moment to register the debug container
    time.sleep(2)

    # Get the new list of ephemeral containers
    new_containers = get_existing_ephemeral_containers(pod_name, namespace)

    # Find the newly created container
    new_container_names = [
        name for name in new_containers if name not in existing_containers
    ]

    if not new_container_names:
        err_console.print(
            "[error]Error:[/] Could not identify newly created debug container"
        )
        return None

    debug_container = new_container_names[0]
    console.print(
        f"[success]✓[/] Created debug container: [pod]{escape(debug_container)}[/]"
    )

    # Wait for the container to actually be running
    if not wait_for_container_running(pod_name, namespace, debug_container):
        err_console.print("[error]Error:[/] Debug container failed to start")
        return None

    return debug_container


def cleanup_debug_container(
    pod_name: str, namespace: str, debug_container: str
) -> bool:
    """Attempt to clean up the debug container."""
    console.print("\n[warning]Cleaning up debug container...[/]")

    # Kill the sleep process in the debug container
    cmd = (
        f"{kubectl_base_cmd()} exec {pod_name} "
        f"-n {namespace} "
        f"-c {debug_container} "
        f"-- /bin/bash -c 'kill -9 1' 2>/dev/null || true"
    )

    run_command(cmd, check=False)

    console.print("[success]✓[/] Debug container cleanup initiated")
    return True


def _output_completion_script(shell: str) -> None:
    """Output the shell completion script and exit."""
    files = {"bash": "kdebug.bash", "zsh": "_kdebug", "fish": "kdebug.fish"}
    filename = files.get(shell)
    if not filename:
        err_console.print(f"[error]Unknown shell:[/] {escape(shell)}")
        sys.exit(1)

    try:
        completions_pkg = importlib.resources.files("kdebug.completions")
        script = (completions_pkg / filename).read_text()
        print(script)
    except Exception as e:
        err_console.print(
            f"[error]Error reading completion script:[/] {escape(str(e))}"
        )
        sys.exit(1)


def parse_controller_arg(value: str) -> Tuple[str, str]:
    """Parse --controller TYPE/NAME format and return (controller_type, controller_name).

    Raises argparse.ArgumentTypeError on invalid input.
    """
    if "/" not in value:
        raise argparse.ArgumentTypeError(
            f"Invalid format '{value}'. Expected TYPE/NAME (e.g. sts/myapp, deploy/frontend)."
        )
    controller_type, controller_name = value.split("/", 1)
    if not controller_name:
        raise argparse.ArgumentTypeError(
            "Missing controller name after '/'. Expected TYPE/NAME (e.g. sts/myapp)."
        )
    if controller_type.lower() not in CONTROLLER_ALIASES:
        valid_types = ", ".join(sorted(CONTROLLER_ALIASES.keys()))
        raise argparse.ArgumentTypeError(
            f"Unknown controller type '{controller_type}'. Valid types: {valid_types}"
        )
    return (controller_type, controller_name)


class KdebugHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter for consistent help alignment."""

    def __init__(self, prog, indent_increment=2, max_help_position=30, width=80):
        super().__init__(prog, indent_increment, max_help_position, width)


def main():
    """Main function to orchestrate the debug container utility."""
    global DEBUG_MODE
    from kdebug.backup import BACKUP_LOCAL_PATH_DEFAULT, create_backup  # noqa: PLC0415
    from kdebug.debug import exec_interactive  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="kdebug",
        description="""TUI for Kubernetes Debug Containers.
https://github.com/jessegoodier/kdebug

Usage:
  kdebug [options]   Interactive debug (default)
  kdebug debug -h    Show debug options
  kdebug backup -h   Show backup options""",
        formatter_class=KdebugHelpFormatter,
        epilog="""Examples:
  kdebug                                                  # Interactive TUI
  kdebug -n prod                                          # TUI, different namespace
  kdebug debug --cmd sh --debug-image docker.io/busybox   # TUI, with sh/busybox
  kdebug backup --pod web-0 --container-path /app/config  # Backup files""",
    )

    # Version flag
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Shared arguments (on main parser so bare `kdebug --pod foo` works)
    target_group = parser.add_argument_group("Target Selection")
    target_group.add_argument(
        "--pod", metavar="NAME", help="Pod name for direct selection"
    )
    target_group.add_argument(
        "--controller",
        type=parse_controller_arg,
        metavar="TYPE/NAME",
        help="Controller as TYPE/NAME (e.g. sts/myapp, deploy/frontend)",
    )

    options_group = parser.add_argument_group("Options")
    options_group.add_argument(
        "-n",
        "--namespace",
        metavar="NS",
        help="Kubernetes namespace (default: current context)",
    )
    options_group.add_argument(
        "--context", metavar="NAME", help="Kubernetes context to use"
    )
    options_group.add_argument(
        "--kubeconfig", metavar="PATH", help="Path to kubeconfig file"
    )
    options_group.add_argument(
        "--container",
        metavar="NAME",
        help="Target container for process namespace sharing",
    )
    options_group.add_argument(
        "--debug-image",
        metavar="IMAGE",
        default=None,
        help="Debug image (default: ghcr.io/jessegoodier/toolbox-common:latest)",
    )
    options_group.add_argument(
        "--as-root", action="store_true", help="Run debug container as root (UID 0)"
    )

    util_group = parser.add_argument_group("Utility")
    util_group.add_argument(
        "--verbose", action="store_true", help="Show kubectl commands being executed"
    )
    util_group.add_argument(
        "--completions",
        choices=["bash", "zsh", "fish"],
        metavar="SHELL",
        help="Output shell completion script",
    )

    # Debug-specific args also registered on the main parser so that naked usage
    # (no explicit "debug" subcommand) can accept them without argparse treating
    # their values as the subcommand positional.
    parser.add_argument("--cmd", metavar="CMD", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--cd-into", metavar="DIR", default=None, help=argparse.SUPPRESS
    )

    # Shared parent parser so subcommands accept target/options args too.
    # Without this, `kdebug backup --pod foo` fails because argparse routes
    # args after the subcommand name to the subparser, which doesn't know
    # about --pod/--controller/etc.
    _shared = argparse.ArgumentParser(
        add_help=False, formatter_class=KdebugHelpFormatter
    )
    _shared_target = _shared.add_argument_group("Target Selection")
    _shared_target.add_argument(
        "--pod", metavar="NAME", help="Pod name for direct selection"
    )
    _shared_target.add_argument(
        "--controller",
        type=parse_controller_arg,
        metavar="TYPE/NAME",
        help="Controller as TYPE/NAME (e.g. sts/myapp, deploy/frontend)",
    )
    _shared_opts = _shared.add_argument_group("Options")
    _shared_opts.add_argument(
        "-n",
        "--namespace",
        metavar="NS",
        help="Kubernetes namespace (default: current context)",
    )
    _shared_opts.add_argument(
        "--context", metavar="NAME", help="Kubernetes context to use"
    )
    _shared_opts.add_argument(
        "--kubeconfig", metavar="PATH", help="Path to kubeconfig file"
    )
    _shared_opts.add_argument(
        "--container",
        metavar="NAME",
        help="Target container for process namespace sharing",
    )
    _shared_opts.add_argument(
        "--debug-image",
        metavar="IMAGE",
        default=None,
        help="Debug image (default: ghcr.io/jessegoodier/toolbox-common:latest)",
    )
    _shared_opts.add_argument(
        "--as-root", action="store_true", help="Run debug container as root (UID 0)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command")

    # debug subcommand
    debug_parser = subparsers.add_parser(
        "debug",
        help="Interactive debug session (default)",
        formatter_class=KdebugHelpFormatter,
        parents=[_shared],
    )
    debug_parser.add_argument(
        "--cmd",
        metavar="CMD",
        default=None,
        help="Command to run in debug container (default: bash)",
    )
    debug_parser.add_argument(
        "--cd-into",
        metavar="DIR",
        help="Change to directory on start (via /proc/1/root)",
    )
    debug_parser.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)

    # backup subcommand
    backup_parser = subparsers.add_parser(
        "backup",
        help="Backup files from pod",
        formatter_class=KdebugHelpFormatter,
        parents=[_shared],
    )
    backup_parser.add_argument(
        "--container-path",
        metavar="PATH",
        required=True,
        help="Path inside the container to back up",
    )
    backup_parser.add_argument(
        "--local-path",
        metavar="TEMPLATE",
        default=None,
        help=f"Local destination (default: {BACKUP_LOCAL_PATH_DEFAULT}). "
        "Supports template variables: {namespace}, {pod}, {date}, {container}",
    )
    backup_parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress backup as tar.gz",
    )
    backup_parser.add_argument(
        "--tar-exclude",
        metavar="PATH",
        action="append",
        dest="tar_exclude",
        default=None,
        help="Exclude a path when using --compress; may be repeated. "
        "/proc/1/root is prepended automatically.",
    )
    backup_parser.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Default to "debug" when no subcommand is given
    if args.command is None:
        args.command = "debug"
        # --cmd and --cd-into are also registered on the main parser (with
        # SUPPRESS) so they're already populated when no subcommand is given.
        # Nothing extra needed here.

    # Apply config file defaults (CLI args > config file > hardcoded defaults)
    config = load_config()
    from_config = set()  # Track which values came from config file

    if not args.debug_image and config.get("debugImage"):
        from_config.add("debug_image")
    args.debug_image = (
        args.debug_image
        or config.get("debugImage")
        or _HARDCODED_DEFAULTS["debugImage"]
    )
    if args.command == "debug":
        if not args.cmd and config.get("cmd"):
            from_config.add("cmd")
        args.cmd = args.cmd or config.get("cmd") or _HARDCODED_DEFAULTS["cmd"]
        if not args.cd_into and config.get("cdInto"):
            from_config.add("cd_into")
        args.cd_into = args.cd_into or config.get("cdInto")
    elif args.command == "backup":
        if not args.local_path and config.get("backupLocalPath"):
            from_config.add("local_path")
        args.local_path = (
            args.local_path
            or config.get("backupLocalPath")
            or BACKUP_LOCAL_PATH_DEFAULT
        )
        args.container_path = args.container_path or config.get("backupContainerPath")

    # Handle --completions early
    if args.completions:
        _output_completion_script(args.completions)
        sys.exit(0)

    # Set debug mode and kubectl global options
    DEBUG_MODE = args.verbose
    global KUBECTL_CONTEXT, KUBECTL_KUBECONFIG
    KUBECTL_CONTEXT = args.context
    KUBECTL_KUBECONFIG = args.kubeconfig

    # Select pod
    pod = select_pod(args)
    if not pod:
        sys.exit(1)

    pod_name = pod["name"]
    namespace = pod["namespace"]

    # Auto-select container if not specified
    target_container = args.container
    if not target_container:
        container_info = get_pod_containers(pod_name, namespace)
        regular_containers = container_info["containers"]

        if not regular_containers:
            err_console.print("[error]Error:[/] No regular containers found in pod")
            sys.exit(1)

        target_container = regular_containers[0]
        console.print(
            f"No --container specified, auto-selecting first non-ephemeral container: [pod]{escape(target_container)}[/]"
        )

    # Build config source annotation path
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    config_path = os.path.join(config_home, "kdebug", "kdebug.json")

    def _val(value: str, key: str) -> Text:
        """Format a value with config source annotation if applicable."""
        t = Text(str(value), style="pod")
        if key in from_config:
            t.append(f" (from {config_path})", style="config_src")
        return t

    summary = Table.grid(padding=(0, 1))
    summary.add_column(style="bold", no_wrap=True)
    summary.add_column()
    summary.add_row("Namespace:", Text(namespace, style="namespace"))
    summary.add_row("Target Pod:", Text(pod_name, style="pod"))
    summary.add_row("Target Container:", Text(target_container, style="container"))
    summary.add_row("Debug Image:", _val(args.debug_image, "debug_image"))
    if args.command == "debug":
        summary.add_row("Command:", _val(args.cmd, "cmd"))
        if args.cd_into:
            summary.add_row("Directory:", _val(args.cd_into, "cd_into"))
    elif args.command == "backup":
        assert args.container_path is not None  # required=True in backup subparser
        summary.add_row("Container Path:", Text(args.container_path, style="container"))
        summary.add_row("Local Path:", _val(args.local_path, "local_path"))
    console.print(
        Panel(
            summary,
            title="[menu_title]Configuration[/]",
            border_style="border",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )

    # Get existing ephemeral containers
    existing_containers = get_existing_ephemeral_containers(pod_name, namespace)

    # Check if we can reuse an existing debug container
    debug_container = None
    if existing_containers:
        console.print(
            f"Found existing ephemeral containers: [dim]{escape(', '.join(existing_containers))}[/]"
        )
        console.print("[namespace]Creating new debug container...[/]")

    # Detect target container UID for the debug container
    run_as_user = None
    if not args.as_root:
        run_as_user = get_container_run_as_user(pod_name, namespace, target_container)

    # Launch debug container
    debug_container = launch_debug_container(
        pod_name,
        namespace,
        args.debug_image,
        target_container,
        existing_containers,
        args.as_root,
        run_as_user,
    )

    if not debug_container:
        err_console.print("[error]Failed to launch debug container[/]")
        sys.exit(1)

    exit_code = 0
    try:
        if args.command == "backup":
            assert args.container_path is not None  # required=True in backup subparser
            success = create_backup(
                pod_name,
                namespace,
                debug_container,
                args.container_path,
                args.local_path,
                args.compress,
                getattr(args, "tar_exclude", None) or [],
            )
            exit_code = 0 if success else 1
        else:
            exit_code = exec_interactive(
                pod_name, namespace, debug_container, args.cmd, cd_into=args.cd_into
            )
    except KeyboardInterrupt:
        console.print("\n[warning]Interrupted by user[/]")
        exit_code = 130
    except Exception as e:
        err_console.print(f"[error]✗ Error:[/] {escape(str(e))}")
        exit_code = 1
    finally:
        cleanup_debug_container(pod_name, namespace, debug_container)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

# Made with Bob
