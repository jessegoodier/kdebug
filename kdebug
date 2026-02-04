#!/usr/bin/env python3

"""
kdebug.py - Universal Kubernetes Debug Container Utility

A utility for launching ephemeral debug containers in Kubernetes pods with
interactive shell access and backup capabilities.

Usage Examples:
    # Interactive session with controller
    ./kdebug.py -n kubecost --controller sts --controller-name aggregator --container aggregator --cmd bash

    # Interactive session with direct pod
    ./kdebug.py -n kubecost --pod aggregator-0 --container aggregator

    # Backup mode
    ./kdebug.py -n kubecost --pod aggregator-0 --container aggregator --backup /var/configs

    # Using deployment
    ./kdebug.py -n myapp --controller deployment --controller-name frontend --cmd sh
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# Global debug flag
DEBUG_MODE = False

# ANSI Color codes (kubecolor-style)


class Colors:
    # Basic colors
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright foreground colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'


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
    cmd = "kubectl config view --minify --output 'jsonpath={..namespace}'"
    output = run_command(cmd, check=False)
    return output if output else "default"


def get_pod_by_name(pod_name: str, namespace: str) -> Optional[Dict]:
    """Get pod information by name."""
    print(
        f"Looking up pod {colorize(pod_name, Colors.CYAN)} in namespace {colorize(namespace, Colors.MAGENTA)}...")

    cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
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
        print(
            f"Error: Unknown controller type '{controller_type}'", file=sys.stderr)
        print(
            f"Supported types: {', '.join(CONTROLLER_ALIASES.keys())}", file=sys.stderr
        )
        return []

    print(
        f"Searching for pods from {colorize(controller_kind, Colors.YELLOW)} {colorize(controller_name, Colors.CYAN)} in namespace {colorize(namespace, Colors.MAGENTA)}..."
    )

    # Get all pods in the namespace
    cmd = f"kubectl get pods -n {namespace} -o json"
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
                matching_pods.append(
                    {"name": pod_name, "namespace": namespace})
                pod_matched = True
                break

        # For Deployments, check if owned by a ReplicaSet that belongs to our Deployment
        if controller_kind == "Deployment" and not pod_matched:
            for ref in owner_refs:
                if ref.get("kind") == "ReplicaSet":
                    rs_name = ref.get("name", "")
                    # ReplicaSet names typically start with deployment name
                    if rs_name.startswith(controller_name + "-"):
                        matching_pods.append(
                            {"name": pod_name, "namespace": namespace})
                        pod_matched = True
                        break

    return matching_pods


def select_pod(args) -> Optional[Dict]:
    """Select a pod based on provided arguments."""
    namespace = args.namespace or get_current_namespace()

    # Direct pod selection
    if args.pod:
        return get_pod_by_name(args.pod, namespace)

    # Controller-based selection
    if args.controller:
        if not args.controller_name:
            print(
                "Error: --controller-name is required when using --controller",
                file=sys.stderr,
            )
            return None

        pods = get_pods_by_controller(
            args.controller, args.controller_name, namespace)

        if not pods:
            print(
                f"No pods found for {args.controller} '{args.controller_name}'",
                file=sys.stderr,
            )
            return None

        if len(pods) > 1:
            print(
                f"Found {colorize(str(len(pods)), Colors.YELLOW)} pods, selecting first one: {colorize(pods[0]['name'], Colors.CYAN)}")

        return pods[0]

    print("Error: Either --pod or --controller must be specified", file=sys.stderr)
    return None


def get_pod_containers(pod_name: str, namespace: str) -> Dict[str, List[str]]:
    """Get all containers from a pod, separated by type."""
    cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
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
        f"Waiting for container {colorize(container_name, Colors.CYAN)} to be running...")

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
        cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
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
                            f"{colorize('✓', Colors.GREEN)} Container {colorize(container_name, Colors.CYAN)} is {colorize('running', Colors.GREEN)}")
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
                                    f"{colorize('Error details:', Colors.RED)} {message}", file=sys.stderr)
                            return False

                        # Show progress for transient states
                        if reason != last_reason:
                            print(
                                f"Container status: {colorize(reason, Colors.YELLOW)}")
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
                                f"{colorize('Error details:', Colors.RED)} {message}", file=sys.stderr)
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
        f"{colorize('✗', Colors.RED)} Timeout ({timeout}s) waiting for container to start", file=sys.stderr)
    if last_reason:
        print(
            f"Last known status: {colorize(last_reason, Colors.YELLOW)}", file=sys.stderr)
    return False


def launch_debug_container(
    pod_name: str,
    namespace: str,
    debug_image: str,
    target_container: Optional[str],
    existing_containers: List[str],
    as_root: bool = False,
) -> Optional[str]:
    """Launch a debug container attached to the pod and return its name."""
    print(
        f"Launching debug container for pod {colorize(pod_name, Colors.CYAN)}...")

    if existing_containers:
        print(
            f"Existing ephemeral containers: {colorize(', '.join(existing_containers), Colors.BRIGHT_BLACK)}")

    # Build kubectl debug command
    cmd_parts = [
        "nohup kubectl debug -i --tty",
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
        cmd_parts.append(
            '--custom=<(echo \'{"securityContext":{"runAsUser":0}}\')')

    cmd_parts.extend(
        [
            f"--image={debug_image}",
            "-- sleep 300 > /dev/null 2>&1 &",
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
    print(f"{colorize('✓', Colors.GREEN)} Created debug container: {colorize(debug_container, Colors.CYAN)}")

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
    print(f"{colorize('Starting interactive session', Colors.BOLD)} in pod {colorize(pod_name, Colors.CYAN)}")
    print(f"Container: {colorize(container_name, Colors.CYAN)}")
    print(f"Command: {colorize(cmd, Colors.YELLOW)}")
    if cd_into:
        print(f"Directory: {colorize(cd_into, Colors.MAGENTA)}")
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
    kubectl_cmd = [
        "kubectl",
        "exec",
        "-it",
        pod_name,
        "-n",
        namespace,
        "-c",
        container_name,
        "--",
    ]

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
    pod_name: str, namespace: str, container_name: str, backup_path: str, compress: bool = False
) -> bool:
    """Create a backup of the specified path and copy it locally."""
    print(f"\n{colorize('=' * 60, Colors.BLUE)}")
    print(f"{colorize('Creating backup', Colors.BOLD)} from pod {colorize(pod_name, Colors.CYAN)}")
    print(f"Path: {colorize(backup_path, Colors.MAGENTA)}")
    if compress:
        print(f"Mode: {colorize('Compressed (tar.gz)', Colors.YELLOW)}")
    else:
        print(f"Mode: {colorize('Direct copy (uncompressed)', Colors.YELLOW)}")
    print(f"{colorize('=' * 60, Colors.BLUE)}\n")

    # Verify the backup path exists in the container using ls
    print(f"{colorize('Verifying backup path exists...', Colors.YELLOW)}")
    verify_cmd = (
        f"kubectl exec {pod_name} "
        f"-n {namespace} "
        f"-c {container_name} "
        f"-- ls -d {backup_path} 2>/dev/null"
    )

    result = run_command(verify_cmd, check=False)
    if not result or result.strip() == "":
        print(f"{colorize('✗ Error:', Colors.RED)} Path {colorize(backup_path, Colors.MAGENTA)} does not exist in container", file=sys.stderr)

        # Try to provide helpful context by checking parent directory
        parent_dir = os.path.dirname(backup_path)
        if parent_dir and parent_dir != "/":
            print(
                f"{colorize('Checking parent directory:', Colors.YELLOW)} {parent_dir}")
            parent_cmd = (
                f"kubectl exec {pod_name} "
                f"-n {namespace} "
                f"-c {container_name} "
                f"-- ls -la {parent_dir} 2>/dev/null | head -20"
            )
            parent_result = run_command(parent_cmd, check=False)
            if parent_result:
                print(
                    f"{colorize('Contents:', Colors.BRIGHT_BLACK)}\n{parent_result}")

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
            f"kubectl exec {pod_name} "
            f"-n {namespace} "
            f"-c {container_name} "
            f"-- /bin/bash -c '{backup_cmd}'"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Backup command failed",
                  file=sys.stderr)
            return False

        print(f"{colorize('✓', Colors.GREEN)} Backup archive created")

        # Copy backup to local machine
        print(f"{colorize('Copying backup to local machine...', Colors.YELLOW)}")

        local_filename = f"{backup_dir}/{date_string}_{pod_name}.tar.gz"

        cmd = (
            f"kubectl cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:/tmp/kdebug-backup.tar.gz "
            f"{local_filename}"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Failed to copy backup",
                  file=sys.stderr)
            return False

        print(
            f"{colorize('✓', Colors.GREEN)} Backup saved to: {colorize(local_filename, Colors.GREEN)}")

        # Cleanup remote backup file
        cleanup_cmd = f"kubectl exec {pod_name} -n {namespace} -c {container_name} -- rm -f /tmp/kdebug-backup.tar.gz"
        run_command(cleanup_cmd, check=False)

    else:
        # Direct copy without compression
        print(f"{colorize('Copying files directly (uncompressed)...', Colors.YELLOW)}")

        # Determine if backup_path is a file or directory for naming
        local_filename = f"{backup_dir}/{date_string}_{pod_name}"

        cmd = (
            f"kubectl cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:{backup_path} "
            f"{local_filename}"
        )

        result = run_command(cmd, check=False)

        if result is None:
            print(f"{colorize('✗', Colors.RED)} Failed to copy backup",
                  file=sys.stderr)
            return False

        print(
            f"{colorize('✓', Colors.GREEN)} Backup saved to: {colorize(local_filename, Colors.GREEN)}")

    return True


def cleanup_debug_container(
    pod_name: str, namespace: str, debug_container: str
) -> bool:
    """Attempt to clean up the debug container."""
    print(f"\n{colorize('Cleaning up debug container...', Colors.YELLOW)}")

    # Kill the sleep process in the debug container
    cmd = (
        f"kubectl exec {pod_name} "
        f"-n {namespace} "
        f"-c {debug_container} "
        f"-- /bin/bash -c 'kill -9 1' 2>/dev/null || true"
    )

    run_command(cmd, check=False)

    print(f"{colorize('✓', Colors.GREEN)} Debug container cleanup initiated")
    return True


def main():
    """Main function to orchestrate the debug container utility."""
    global DEBUG_MODE

    parser = argparse.ArgumentParser(
        description="Universal Kubernetes Debug Container Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive session with controller
  %(prog)s -n kubecost --controller sts --controller-name aggregator --container aggregator --cmd bash

  # Interactive session with direct pod
  %(prog)s -n kubecost --pod aggregator-0 --container aggregator

  # Change into specific directory
  %(prog)s -n kubecost --pod aggregator-0 --container aggregator --cd-into /var/configs

  # Backup mode
  %(prog)s -n kubecost --pod aggregator-0 --container aggregator --backup /var/configs

  # Using deployment
  %(prog)s -n myapp --controller deployment --controller-name frontend --cmd sh
        """,
    )

    # Pod selection arguments
    pod_group = parser.add_argument_group("pod selection")
    pod_group.add_argument("--pod", help="Pod name (direct selection)")
    pod_group.add_argument(
        "--controller",
        choices=list(CONTROLLER_ALIASES.keys()),
        help="Controller type (deployment, statefulset, daemonset, or aliases: deploy, sts, ds)",
    )
    pod_group.add_argument(
        "--controller-name", help="Controller name (required with --controller)"
    )

    # Configuration arguments
    config_group = parser.add_argument_group("configuration")
    config_group.add_argument(
        "-n",
        "--namespace",
        help="Kubernetes namespace (default: current context namespace)",
    )
    config_group.add_argument(
        "--container", help="Target container name (for --target flag in kubectl debug)"
    )
    config_group.add_argument(
        "--debug-image",
        default="ghcr.io/jessegoodier/toolbox:latest",
        help="Debug container image (default: ubuntu-based debug image)",
    )

    # Operation arguments
    operation_group = parser.add_argument_group("operations")
    operation_group.add_argument(
        "--cmd",
        default="bash",
        help="Command to run in debug container (default: bash)",
    )
    operation_group.add_argument(
        "--cd-into", help="Start shell session in specified directory"
    )
    operation_group.add_argument(
        "--backup", metavar="PATH", help="Create backup of specified path"
    )
    operation_group.add_argument(
        "--compress", action="store_true", help="Compress backup with tar.gz (only with --backup)"
    )
    operation_group.add_argument(
        "--as-root", action="store_true", help="Run debug container as root user (UID 0)"
    )

    # Utility arguments
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode (show kubectl commands)"
    )

    args = parser.parse_args()

    # Set debug mode
    DEBUG_MODE = args.debug

    # Validate arguments
    if not args.pod and not args.controller:
        parser.error("Either --pod or --controller must be specified")

    if args.controller and not args.controller_name:
        parser.error("--controller-name is required when using --controller")

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
    print(f"{colorize('Target Pod:', Colors.BOLD)} {colorize(pod_name, Colors.CYAN)}")
    print(f"{colorize('Namespace:', Colors.BOLD)} {colorize(namespace, Colors.MAGENTA)}")
    print(f"{colorize('Target Container:', Colors.BOLD)} {colorize(target_container, Colors.CYAN)}")
    print(f"{colorize('Debug Image:', Colors.BOLD)} {colorize(args.debug_image, Colors.BRIGHT_BLACK)}")
    print(f"{colorize('=' * 60, Colors.BLUE)}\n")

    # Get existing ephemeral containers
    existing_containers = get_existing_ephemeral_containers(
        pod_name, namespace)

    # Check if we can reuse an existing debug container
    debug_container = None
    if existing_containers:
        print(
            f"Found existing ephemeral containers: {colorize(', '.join(existing_containers), Colors.BRIGHT_BLACK)}")
        # For simplicity, we'll create a new one. In production, you might want to reuse.
        print(f"{colorize('Creating new debug container...', Colors.YELLOW)}")

    # Launch debug container
    debug_container = launch_debug_container(
        pod_name, namespace, args.debug_image, target_container, existing_containers, args.as_root
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
                pod_name, namespace, debug_container, args.backup, args.compress)
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
