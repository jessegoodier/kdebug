"""kdebug.debug - Interactive exec subcommand implementation."""

import subprocess
from typing import Optional

import rich.box as box
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

import kdebug.cli as _cli


def exec_interactive(
    pod_name: str, namespace: str, container_name: str, cmd: str, cd_into: Optional[str]
) -> int:
    """Execute an interactive command in the debug container."""
    t = Text()
    t.append("Pod:       ", "bold")
    t.append(f"{pod_name}\n", "pod")
    t.append("Container: ", "bold")
    t.append(f"{container_name}\n", "container")
    t.append("Command:   ", "bold")
    t.append(f"{cmd}\n", "info")
    if cd_into:
        t.append("Directory: ", "bold")
        t.append(cd_into, "info")
    _cli.console.print(
        Panel(
            t,
            title="[menu_title]Starting interactive session[/]",
            border_style="border",
            box=box.HEAVY,
            padding=(0, 2),
        )
    )

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
    if _cli.KUBECTL_KUBECONFIG:
        kubectl_cmd.extend(["--kubeconfig", _cli.KUBECTL_KUBECONFIG])
    if _cli.KUBECTL_CONTEXT:
        kubectl_cmd.extend(["--context", _cli.KUBECTL_CONTEXT])
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

    _cli.print_debug_command(" ".join(kubectl_cmd))

    try:
        # Use subprocess.run without capture_output for interactive TTY
        result = subprocess.run(kubectl_cmd)
        return result.returncode
    except KeyboardInterrupt:
        _cli.console.print("\n\n[info]Interrupted by user[/]")
        return 130
    except Exception as e:
        _cli.err_console.print(
            f"[error]Error executing interactive command:[/] {escape(str(e))}"
        )
        return 1
