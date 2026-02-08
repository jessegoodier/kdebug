#!/usr/bin/env python3

"""
kdebug.py - Universal Kubernetes Debug Container Utility

A utility for launching ephemeral debug containers in Kubernetes pods with
interactive shell access and backup capabilities.

Usage Examples:
    # Interactive session with controller
    ./kdebug.py -n kubecost --controller sts/aggregator --container aggregator --cmd bash

    # Interactive session with direct pod
    ./kdebug.py -n kubecost --pod aggregator-0 --container aggregator

    # Backup mode
    ./kdebug.py -n kubecost --pod aggregator-0 --container aggregator --backup /var/configs

    # Using deployment
    ./kdebug.py -n myapp --controller deploy/frontend --cmd sh
"""

import argparse
import importlib.resources
import json
import os
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from kdebug import __version__

# Global debug flag
DEBUG_MODE = False

# Global kubectl options (set after argument parsing)
KUBECTL_CONTEXT = None
KUBECTL_KUBECONFIG = None

# ANSI Color codes (kubecolor-style)


class Colors:
    # Basic colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


def colorize(text: str, color: str) -> str:
    """Wrap text with color codes."""
    return f"{color}{text}{Colors.RESET}"


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
        print(f"\n{'─' * 60}")
        print("🔍 DEBUG: Executing command:")
        print(f"{'─' * 60}")
        print(f"{cmd}")
        print(f"{'─' * 60}\n")


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
        print(f"Error running command: {cmd}", file=sys.stderr)
        print(f"Error: {e.stderr}", file=sys.stderr)
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


def validate_cluster_connection(namespace: str) -> Optional[str]:
    """Validate kubectl can connect to the cluster and namespace exists.

    Returns None on success, or an error message string on failure.
    """
    cmd = f"{kubectl_base_cmd()} get namespace {namespace} -o name"
    print_debug_command(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip()
    return None


def get_pod_by_name(pod_name: str, namespace: str) -> Optional[Dict]:
    """Get pod information by name."""
    print(
        f"Looking up pod {colorize(pod_name, Colors.CYAN)} in namespace {colorize(namespace, Colors.MAGENTA)}..."
    )

    cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        print(
            f"{colorize('✗ Error:', Colors.RED)} Pod '{pod_name}' not found in namespace '{namespace}'",
            file=sys.stderr,
        )
        return None

    try:
        pod_data = json.loads(output)
        return {
            "name": pod_data.get("metadata", {}).get("name", ""),
            "namespace": namespace,
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing pod JSON: {e}", file=sys.stderr)
        return None


def get_pods_by_controller(
    controller_type: str, controller_name: str, namespace: str
) -> List[Dict]:
    """Get all pods owned by a specific controller using owner references."""
    # Normalize controller type
    controller_kind = CONTROLLER_ALIASES.get(controller_type.lower())
    if not controller_kind:
        print(f"Error: Unknown controller type '{controller_type}'", file=sys.stderr)
        print(
            f"Supported types: {', '.join(CONTROLLER_ALIASES.keys())}", file=sys.stderr
        )
        return []

    print(
        f"Searching for pods from {colorize(controller_kind, Colors.YELLOW)} {colorize(controller_name, Colors.CYAN)} in namespace {colorize(namespace, Colors.MAGENTA)}..."
    )

    # Get all pods in the namespace
    cmd = f"{kubectl_base_cmd()} get pods -n {namespace} -o json"
    output = run_command(cmd, check=False)

    if not output:
        print("Error: Failed to get pods", file=sys.stderr)
        return []

    try:
        pods_data = json.loads(output)
    except json.JSONDecodeError as e:
        print(f"Error parsing pods JSON: {e}", file=sys.stderr)
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


def display_menu(
    title: str, items: List[str], selected_idx: int, show_numbers: bool = True
):
    """Display a colorful menu with the selected item highlighted."""
    # Clear screen
    print("\033[2J\033[H", end="")

    # Print title
    print(f"\n{colorize('═' * 70, Colors.BLUE)}")
    print(f"{colorize(title, Colors.BOLD + Colors.BRIGHT_CYAN)}")
    print(f"{colorize('═' * 70, Colors.BLUE)}\n")

    # Print items
    for idx, item in enumerate(items):
        if idx == selected_idx:
            # Highlighted item
            prefix = "▶ " if show_numbers else "  "
            number = f"{idx + 1}. " if show_numbers else ""
            print(
                f"{colorize(prefix + number + item, Colors.BOLD + Colors.BRIGHT_GREEN)}"
            )
        else:
            # Normal item
            prefix = "  "
            number = f"{idx + 1}. " if show_numbers else ""
            print(f"{colorize(prefix + number + item, Colors.WHITE)}")

    # Print quit option as selectable item
    quit_idx = len(items)
    if selected_idx == quit_idx:
        print(f"\n{colorize('▶ q. Quit', Colors.BOLD + Colors.BRIGHT_GREEN)}")
    else:
        print(f"\n  {colorize('q.', Colors.WHITE)} {colorize('Quit', Colors.CYAN)}")

    # Print instructions
    print(f"\n{colorize('─' * 70, Colors.DIM)}")
    if show_numbers:
        print(
            f"{colorize('Use ↑/↓ arrows or numbers to select, Enter to confirm', Colors.BRIGHT_BLACK)}"
        )
    else:
        print(
            f"{colorize('Use ↑/↓ arrows to select, Enter to confirm', Colors.BRIGHT_BLACK)}"
        )
    print(f"{colorize('─' * 70, Colors.DIM)}\n")


def interactive_menu(
    title: str, items: List[str], show_numbers: bool = True
) -> Optional[int]:
    """Display an interactive menu and return the selected index."""
    if not items:
        print(f"{colorize('✗ Error:', Colors.RED)} No items to display")
        return None

    selected_idx = 0
    quit_idx = len(items)  # Quit is one position after last item

    while True:
        display_menu(title, items, selected_idx, show_numbers)

        key = read_key()

        if key == "up":
            selected_idx = (selected_idx - 1) % (len(items) + 1)
        elif key == "down":
            selected_idx = (selected_idx + 1) % (len(items) + 1)
        elif key == "\r" or key == "\n":  # Enter
            if selected_idx == quit_idx:
                return None  # Quit selected
            return selected_idx
        elif key == "q" or key == "Q":
            return None
        elif key.isdigit() and show_numbers:
            num = int(key)
            if 1 <= num <= len(items):
                selected_idx = num - 1
                return selected_idx


def select_controller_interactive(namespace: str) -> Optional[Tuple[str, str]]:
    """Interactive TUI for selecting a controller."""
    print(f"\n{colorize('Fetching controllers...', Colors.YELLOW)}")
    controllers = get_all_controllers(namespace)

    # Flatten controllers into menu items
    menu_items = []
    controller_map = []

    for kind in ["Deployment", "StatefulSet", "DaemonSet"]:
        for ctrl in controllers[kind]:
            status = (
                f"{ctrl['ready']}/{ctrl['replicas']}" if ctrl["replicas"] > 0 else "N/A"
            )
            menu_items.append(
                f"{colorize(kind, Colors.YELLOW)} {colorize(ctrl['name'], Colors.CYAN)} "
                f"({colorize(status, Colors.GREEN if ctrl['ready'] == ctrl['replicas'] else Colors.YELLOW)})"
            )
            controller_map.append((ctrl["type"], ctrl["name"]))

    if not menu_items:
        print(
            f"{colorize('✗ Error:', Colors.RED)} No controllers found in namespace {colorize(namespace, Colors.MAGENTA)}"
        )
        return None

    title = f"Select Controller in namespace: {colorize(namespace, Colors.MAGENTA)}"
    selected_idx = interactive_menu(title, menu_items)

    if selected_idx is None:
        return None

    return controller_map[selected_idx]


def select_pod_interactive(namespace: str) -> Optional[str]:
    """Interactive TUI for selecting a pod."""
    print(f"\n{colorize('Fetching pods...', Colors.YELLOW)}")
    pods = get_all_pods(namespace)

    if not pods:
        print(
            f"{colorize('✗ Error:', Colors.RED)} No pods found in namespace {colorize(namespace, Colors.MAGENTA)}"
        )
        return None

    # Create menu items
    menu_items = []
    for pod in pods:
        status_color = Colors.GREEN if pod["status"] == "Running" else Colors.YELLOW
        menu_items.append(
            f"{colorize(pod['name'], Colors.CYAN)} "
            f"({colorize(pod['status'], status_color)})"
        )

    title = f"Select Pod in namespace: {colorize(namespace, Colors.MAGENTA)}"
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
        print(f"{colorize('✗ Error:', Colors.RED)} {error}")
        return None

    # Direct pod selection
    if args.pod:
        return get_pod_by_name(args.pod, namespace)

    # Controller-based selection
    if args.controller:
        controller_type, controller_name = args.controller
        pods = get_pods_by_controller(controller_type, controller_name, namespace)

        if not pods:
            print(
                f"No pods found for {controller_type} '{controller_name}'",
                file=sys.stderr,
            )
            return None

        if len(pods) > 1:
            print(
                f"Found {colorize(str(len(pods)), Colors.YELLOW)} pods, selecting first one: {colorize(pods[0]['name'], Colors.CYAN)}"
            )

        return pods[0]

    # Interactive mode - no pod or controller specified
    print(f"\n{colorize('Starting interactive pod selection...', Colors.CYAN)}")

    # Direct pod selection via TUI
    pod_name = select_pod_interactive(namespace)
    if not pod_name:
        print(f"\n{colorize('Selection cancelled', Colors.CYAN)}")
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
        print(f"Error parsing pod JSON: {e}", file=sys.stderr)
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
    pod_name: str, namespace: str, container_name: str, timeout: int = 60
) -> bool:
    """Poll until the container is in running state or timeout."""
    print(
        f"Waiting for container {colorize(container_name, Colors.CYAN)} to be running..."
    )

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

    while time.time() - start_time < timeout:
        cmd = f"{kubectl_base_cmd()} get pod {pod_name} -n {namespace} -o json"
        output = run_command(cmd)

        if not output:
            time.sleep(2)
            continue

        try:
            pod_data = json.loads(output)
            ephemeral_statuses = pod_data.get("status", {}).get(
                "ephemeralContainerStatuses", []
            )

            for status in ephemeral_statuses:
                if status.get("name") == container_name:
                    state = status.get("state", {})

                    # Check if running
                    if "running" in state:
                        print(
                            f"{colorize('✓', Colors.GREEN)} Container {colorize(container_name, Colors.CYAN)} is {colorize('running', Colors.GREEN)}"
                        )
                        return True

                    # Check if waiting
                    elif "waiting" in state:
                        waiting_info = state.get("waiting", {})
                        reason = waiting_info.get("reason", "Unknown")
                        message = waiting_info.get("message", "")

                        # Check for immediate failure states
                        if reason in failure_states:
                            print(
                                f"{colorize('✗', Colors.RED)} Container failed to start: {colorize(reason, Colors.RED)}",
                                file=sys.stderr,
                            )
                            if message:
                                print(
                                    f"{colorize('Error details:', Colors.RED)} {message}",
                                    file=sys.stderr,
                                )
                            return False

                        # Show progress for transient states
                        if reason != last_reason:
                            print(
                                f"Container status: {colorize(reason, Colors.YELLOW)}"
                            )
                            last_reason = reason

                    # Check if terminated
                    elif "terminated" in state:
                        terminated_info = state.get("terminated", {})
                        reason = terminated_info.get("reason", "Unknown")
                        exit_code = terminated_info.get("exitCode", "N/A")
                        message = terminated_info.get("message", "")

                        print(
                            f"{colorize('✗', Colors.RED)} Container terminated: {colorize(reason, Colors.RED)} (exit code: {colorize(str(exit_code), Colors.RED)})",
                            file=sys.stderr,
                        )
                        if message:
                            print(
                                f"{colorize('Error details:', Colors.RED)} {message}",
                                file=sys.stderr,
                            )
                        return False

                    # Container exists but no state info yet
                    else:
                        if last_reason != "NoState":
                            print("Container status: Initializing...")
                            last_reason = "NoState"

        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse pod JSON: {e}", file=sys.stderr)

        time.sleep(2)

    print(
        f"{colorize('✗', Colors.RED)} Timeout ({timeout}s) waiting for container to start",
        file=sys.stderr,
    )
    if last_reason:
        print(
            f"Last known status: {colorize(last_reason, Colors.YELLOW)}",
            file=sys.stderr,
        )
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

        # Check if there's a runAsUser set at pod level
        pod_run_as_user = pod_security_context.get("runAsUser")

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
    print(f"Launching debug container for pod {colorize(pod_name, Colors.CYAN)}...")

    # Check if running as root is possible when requested
    if as_root:
        security_check = check_pod_security_context(pod_name, namespace)
        if not security_check["can_run_as_root"]:
            print(
                f"{colorize('⚠ Warning:', Colors.YELLOW)} {security_check['reason']}",
                file=sys.stderr,
            )
            print(
                f"{colorize('The --as-root flag will likely fail.', Colors.YELLOW)} Proceeding anyway...",
                file=sys.stderr,
            )
            print(f"{colorize('Tip:', Colors.CYAN)} Try without --as-root flag\n")
    elif run_as_user is not None:
        print(
            f"Running as UID {colorize(str(run_as_user), Colors.CYAN)} (matching target container)"
        )

    # if existing_containers:
    #     print(
    #         f"Existing ephemeral containers: {colorize(', '.join(existing_containers), Colors.BRIGHT_BLACK)}"
    #     )

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
        print(
            "Error: Could not identify newly created debug container", file=sys.stderr
        )
        return None

    debug_container = new_container_names[0]
    print(
        f"{colorize('✓', Colors.GREEN)} Created debug container: {colorize(debug_container, Colors.CYAN)}"
    )

    # Wait for the container to actually be running
    if not wait_for_container_running(pod_name, namespace, debug_container):
        print("Error: Debug container failed to start", file=sys.stderr)
        return None

    return debug_container


def exec_interactive(
    pod_name: str, namespace: str, container_name: str, cmd: str, cd_into: str
) -> int:
    """Execute an interactive command in the debug container."""
    print(f"\n{colorize('=' * 60, Colors.BLUE)}")
    print(f"{colorize('Starting interactive session', Colors.BOLD)} in:")
    print(f"Pod: {colorize(pod_name, Colors.CYAN)}")
    print(f"Container: {colorize(container_name, Colors.CYAN)}")
    print(f"Command: {colorize(cmd, Colors.CYAN)}")
    if cd_into:
        print(f"Directory: {colorize(cd_into, Colors.CYAN)}")
    print(f"{colorize('=' * 60, Colors.BLUE)}\n")

    # If cd_into is specified, wrap command to cd first
    if cd_into:
        if cmd == "bash":
            cmd = f"bash -c 'cd /proc/1/root{cd_into} && exec bash'"
        elif cmd == "sh":
            cmd = f"sh -c 'cd /proc/1/root{cd_into} && exec sh'"
        else:
            # For custom commands, prepend cd
            cmd = f"bash -c 'cd /proc/1/root{cd_into} && {cmd}'"

    # Build kubectl command - handle complex commands with shell
    kubectl_cmd = ["kubectl"]
    if KUBECTL_KUBECONFIG:
        kubectl_cmd.extend(["--kubeconfig", KUBECTL_KUBECONFIG])
    if KUBECTL_CONTEXT:
        kubectl_cmd.extend(["--context", KUBECTL_CONTEXT])
    kubectl_cmd.extend(
        [
            "exec",
            "-it",
            pod_name,
            "-n",
            namespace,
            "-c",
            container_name,
            "--",
        ]
    )

    # Split the command if it's a simple command, otherwise use sh -c
    if cmd.startswith("bash -c") or cmd.startswith("sh -c"):
        # For complex commands, we need to use shell
        kubectl_cmd.extend(["sh", "-c", cmd])
    else:
        # For simple commands, just append
        kubectl_cmd.append(cmd)

    print_debug_command(" ".join(kubectl_cmd))

    try:
        # Use subprocess.run without capture_output for interactive TTY
        result = subprocess.run(kubectl_cmd)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"Error executing interactive command: {e}", file=sys.stderr)
        return 1


def create_backup(
    pod_name: str,
    namespace: str,
    container_name: str,
    backup_path: str,
    compress: bool = False,
) -> bool:
    """Create a backup of the specified path and copy it locally."""
    print(f"\n{colorize('=' * 60, Colors.BLUE)}")
    print(
        f"{colorize('Creating backup', Colors.BOLD)} from pod {colorize(pod_name, Colors.CYAN)}"
    )
    print(f"Path: {colorize(backup_path, Colors.MAGENTA)}")
    if compress:
        print(f"Mode: {colorize('Compressed (tar.gz)', Colors.YELLOW)}")
    else:
        print(f"Mode: {colorize('Direct copy (uncompressed)', Colors.YELLOW)}")
    print(f"{colorize('=' * 60, Colors.BLUE)}\n")

    # Verify the backup path exists in the container using ls
    print(f"{colorize('Verifying backup path exists...', Colors.YELLOW)}")
    verify_cmd = (
        f"{kubectl_base_cmd()} exec {pod_name} "
        f"-n {namespace} "
        f"-c {container_name} "
        f"-- ls -d {backup_path} 2>/dev/null"
    )

    result = run_command(verify_cmd, check=False)
    if not result or result.strip() == "":
        print(
            f"{colorize('✗ Error:', Colors.RED)} Path {colorize(backup_path, Colors.MAGENTA)} does not exist in container",
            file=sys.stderr,
        )

        # Try to provide helpful context by checking parent directory
        parent_dir = os.path.dirname(backup_path)
        if parent_dir and parent_dir != "/":
            print(
                f"{colorize('Checking parent directory:', Colors.YELLOW)} {parent_dir}"
            )
            parent_cmd = (
                f"{kubectl_base_cmd()} exec {pod_name} "
                f"-n {namespace} "
                f"-c {container_name} "
                f"-- ls -la {parent_dir} 2>/dev/null | head -20"
            )
            parent_result = run_command(parent_cmd, check=False)
            if parent_result:
                print(f"{colorize('Contents:', Colors.BRIGHT_BLACK)}\n{parent_result}")

        return False

    print(f"{colorize('✓', Colors.GREEN)} Path exists: {result.strip()}")

    # Create backup directory if it doesn't exist
    backup_dir = f"./backups/{namespace}"
    os.makedirs(backup_dir, exist_ok=True)

    date_string = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if compress:
        # Compressed backup using tar.gz
        print(f"{colorize('Creating tar.gz archive...', Colors.YELLOW)}")
        backup_cmd = f"tar czf /tmp/kdebug-backup.tar.gz {backup_path}"

        cmd = (
            f"{kubectl_base_cmd()} exec {pod_name} "
            f"-n {namespace} "
            f"-c {container_name} "
            f"-- /bin/bash -c '{backup_cmd}'"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Backup command failed", file=sys.stderr)
            return False

        print(f"{colorize('✓', Colors.GREEN)} Backup archive created")

        # Copy backup to local machine
        print(f"{colorize('Copying backup to local machine...', Colors.YELLOW)}")

        local_filename = f"{backup_dir}/{date_string}_{pod_name}.tar.gz"

        cmd = (
            f"{kubectl_base_cmd()} cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:/tmp/kdebug-backup.tar.gz "
            f"{local_filename}"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Failed to copy backup", file=sys.stderr)
            return False

        print(
            f"{colorize('✓', Colors.GREEN)} Backup saved to: {colorize(local_filename, Colors.GREEN)}"
        )

        # Cleanup remote backup file
        cleanup_cmd = f"{kubectl_base_cmd()} exec {pod_name} -n {namespace} -c {container_name} -- rm -f /tmp/kdebug-backup.tar.gz"
        run_command(cleanup_cmd, check=False)

    else:
        # Direct copy without compression
        print(f"{colorize('Copying files directly (uncompressed)...', Colors.YELLOW)}")

        # Determine if backup_path is a file or directory for naming
        local_filename = f"{backup_dir}/{date_string}_{pod_name}"

        cmd = (
            f"{kubectl_base_cmd()} cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:{backup_path} "
            f"{local_filename}"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Failed to copy backup", file=sys.stderr)
            return False

        print(
            f"{colorize('✓', Colors.GREEN)} Backup saved to: {colorize(local_filename, Colors.GREEN)}"
        )

    return True


def cleanup_debug_container(
    pod_name: str, namespace: str, debug_container: str
) -> bool:
    """Attempt to clean up the debug container."""
    print(f"\n{colorize('Cleaning up debug container...', Colors.YELLOW)}")

    # Kill the sleep process in the debug container
    cmd = (
        f"{kubectl_base_cmd()} exec {pod_name} "
        f"-n {namespace} "
        f"-c {debug_container} "
        f"-- /bin/bash -c 'kill -9 1' 2>/dev/null || true"
    )

    run_command(cmd, check=False)

    print(f"{colorize('✓', Colors.GREEN)} Debug container cleanup initiated")
    return True


def _output_completion_script(shell: str) -> None:
    """Output the shell completion script and exit."""
    files = {"bash": "kdebug.bash", "zsh": "_kdebug", "fish": "kdebug.fish"}
    filename = files.get(shell)
    if not filename:
        print(f"Unknown shell: {shell}", file=sys.stderr)
        sys.exit(1)

    try:
        completions_pkg = importlib.resources.files("kdebug.completions")
        script = (completions_pkg / filename).read_text()
        print(script)
    except Exception as e:
        print(f"Error reading completion script: {e}", file=sys.stderr)
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

    parser = argparse.ArgumentParser(
        prog="kdebug",
        description="""Launch ephemeral debug containers in Kubernetes pods.

Usage:
  kdebug [options]                                  Interactive TUI mode
  kdebug --pod POD [options]                        Direct pod selection
  kdebug --controller TYPE/NAME [options]            Controller selection""",
        formatter_class=KdebugHelpFormatter,
        epilog="""Examples:
  kdebug                                         # Interactive TUI
  kdebug -n prod --pod api-0                     # Direct pod
  kdebug --controller sts/db                     # StatefulSet pod
  kdebug --controller deploy/frontend --cmd sh   # Deployment pod
  kdebug --pod web-0 --backup /app/config        # Backup files""",
    )

    # Version flag
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Target selection arguments
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

    # Options arguments
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
        default="ghcr.io/jessegoodier/toolbox:latest",
        help="Debug image (default: ghcr.io/jessegoodier/toolbox:latest)",
    )

    # Operations arguments
    ops_group = parser.add_argument_group("Operations")
    ops_group.add_argument(
        "--cmd",
        metavar="CMD",
        default="bash",
        help="Command to run in debug container (default: bash)",
    )
    ops_group.add_argument(
        "--cd-into",
        metavar="DIR",
        help="Change to directory on start (via /proc/1/root)",
    )
    ops_group.add_argument(
        "--backup",
        metavar="PATH",
        help="Copy path from pod to local ./backups/ directory",
    )
    ops_group.add_argument(
        "--compress",
        action="store_true",
        help="Compress backup as tar.gz (requires --backup)",
    )
    ops_group.add_argument(
        "--as-root", action="store_true", help="Run debug container as root (UID 0)"
    )

    # Utility arguments
    util_group = parser.add_argument_group("Utility")
    util_group.add_argument(
        "--debug", action="store_true", help="Show kubectl commands being executed"
    )
    util_group.add_argument(
        "--completions",
        choices=["bash", "zsh", "fish"],
        metavar="SHELL",
        help="Output shell completion script",
    )

    args = parser.parse_args()

    # Handle --completions early
    if args.completions:
        _output_completion_script(args.completions)
        sys.exit(0)

    # Set debug mode and kubectl global options
    DEBUG_MODE = args.debug
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
            print("Error: No regular containers found in pod", file=sys.stderr)
            sys.exit(1)

        target_container = regular_containers[0]
        print(
            f"No --container specified, auto-selecting first non-ephemeral container: {colorize(target_container, Colors.CYAN)}"
        )

    print(f"\n{colorize('=' * 60, Colors.BLUE)}")
    print(f"{colorize('Namespace:', Colors.BOLD)} {colorize(namespace, Colors.CYAN)}")
    print(f"{colorize('Target Pod:', Colors.BOLD)} {colorize(pod_name, Colors.CYAN)}")
    print(
        f"{colorize('Target Container:', Colors.BOLD)} {colorize(target_container, Colors.CYAN)}"
    )
    print(
        f"{colorize('Debug Image:', Colors.BOLD)} {colorize(args.debug_image, Colors.CYAN)}"
    )
    print(f"{colorize('=' * 60, Colors.BLUE)}\n")

    # Get existing ephemeral containers
    existing_containers = get_existing_ephemeral_containers(pod_name, namespace)

    # Check if we can reuse an existing debug container
    debug_container = None
    if existing_containers:
        print(
            f"Found existing ephemeral containers: {colorize(', '.join(existing_containers), Colors.BRIGHT_BLACK)}"
        )
        # For simplicity, we'll create a new one. In production, you might want to reuse.
        print(f"{colorize('Creating new debug container...', Colors.MAGENTA)}")

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
        print("Failed to launch debug container", file=sys.stderr)
        sys.exit(1)

    exit_code = 0
    try:
        # Execute operation
        if args.backup:
            # Backup mode
            success = create_backup(
                pod_name, namespace, debug_container, args.backup, args.compress
            )
            exit_code = 0 if success else 1
        else:
            # Interactive mode
            exit_code = exec_interactive(
                pod_name, namespace, debug_container, args.cmd, cd_into=args.cd_into
            )
    except KeyboardInterrupt:
        print(f"\n{colorize('Interrupted by user', Colors.YELLOW)}")
        exit_code = 130
    except Exception as e:
        print(f"{colorize('✗ Error:', Colors.RED)} {e}", file=sys.stderr)
        exit_code = 1
    finally:
        # Cleanup - runs after backup/interactive session completes
        cleanup_debug_container(pod_name, namespace, debug_container)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

# Made with Bob
