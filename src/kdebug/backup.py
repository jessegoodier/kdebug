"""kdebug.backup - Backup subcommand implementation."""

import os
import re
from datetime import datetime
from typing import List, Optional

import rich.box as box
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

import kdebug.cli as _cli

BACKUP_LOCAL_PATH_DEFAULT = "./backups/{namespace}/{date}_{pod}"
_BACKUP_TEMPLATE_VARS = {"namespace", "pod", "date", "container"}


def validate_local_path_template(template: str) -> Optional[str]:
    """Validate that a local-path template only uses known variables.

    Returns None on success, or an error message string on failure.
    """
    unknown = set()
    for match in re.finditer(r"\{(\w+)\}", template):
        var = match.group(1)
        if var not in _BACKUP_TEMPLATE_VARS:
            unknown.add(var)
    if unknown:
        available = ", ".join(f"{{{v}}}" for v in sorted(_BACKUP_TEMPLATE_VARS))
        return (
            f"Unknown template variable(s): {', '.join(f'{{{v}}}' for v in sorted(unknown))}. "
            f"Available variables: {available}"
        )
    return None


def expand_local_path(
    template: str, namespace: str, pod_name: str, container_name: str
) -> str:
    """Expand a local-path template with actual values."""
    date_string = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return template.format_map(
        {
            "namespace": namespace,
            "pod": pod_name,
            "date": date_string,
            "container": container_name,
        }
    )


def create_backup(
    pod_name: str,
    namespace: str,
    container_name: str,
    container_path: str,
    local_path_template: str,
    compress: bool = False,
    tar_excludes: Optional[List[str]] = None,
) -> bool:
    """Create a backup of the specified path and copy it locally."""
    # Validate template before doing anything
    template_error = validate_local_path_template(local_path_template)
    if template_error:
        _cli.err_console.print(f"[error]✗ Error:[/] {escape(template_error)}")
        return False

    # Expand the local path template
    local_path = expand_local_path(
        local_path_template, namespace, pod_name, container_name
    )
    if compress:
        local_path += ".tar.gz"

    t = Text()
    t.append("Pod:            ", "bold")
    t.append(f"{pod_name}\n", "pod")
    t.append("Container:      ", "bold")
    t.append(f"{container_name}\n", "container")
    t.append("Container path: ", "bold")
    t.append(f"{container_path}\n", "namespace")
    t.append("Local path:     ", "bold")
    t.append(f"{local_path}\n", "namespace")
    t.append("Mode:           ", "bold")
    if compress:
        t.append("Compressed (tar.gz)", "warning")
    else:
        t.append("Direct copy (uncompressed)", "warning")
    _cli.console.print(
        Panel(
            t,
            title="[menu_title]Creating backup[/]",
            border_style="border",
            box=box.HEAVY,
            padding=(0, 2),
        )
    )

    # Verify the container path exists in the container using ls
    _cli.console.print("[warning]Verifying container path exists...[/]")
    verify_cmd = (
        f"{_cli.kubectl_base_cmd()} exec {pod_name} "
        f"-n {namespace} "
        f"-c {container_name} "
        f"-- ls -d /proc/1/root{container_path} 2>/dev/null"
    )

    result = _cli.run_command(verify_cmd, check=False)
    if not result or result.strip() == "":
        _cli.err_console.print(
            f"[error]✗ Error:[/] Path [namespace]{escape(container_path)}[/] does not exist in container"
        )

        # Try to provide helpful context by checking parent directory
        parent_dir = os.path.dirname(container_path)
        if parent_dir and parent_dir != "/":
            _cli.console.print(
                f"[warning]Checking parent directory:[/] {escape(parent_dir)}"
            )
            parent_cmd = (
                f"{_cli.kubectl_base_cmd()} exec {pod_name} "
                f"-n {namespace} "
                f"-c {container_name} "
                f"-- ls -la /proc/1/root{parent_dir} 2>/dev/null | head -20"
            )
            parent_result = _cli.run_command(parent_cmd, check=False)
            if parent_result:
                _cli.console.print(f"[dim]Contents:[/]\n{escape(parent_result)}")

        return False

    _cli.console.print(f"[success]✓[/] Path exists: {escape(result.strip())}")

    # Create parent directories for local path
    local_dir = os.path.dirname(local_path)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    if compress:
        # Compressed backup using tar.gz.
        # The debug container accesses the target container's filesystem via
        # /proc/1/root, so use -C to make tar treat that as the root.
        container_path_rel = container_path.lstrip("/") or "."
        exclude_flags = " ".join(
            f"--exclude={p.lstrip('/')}" for p in (tar_excludes or [])
        )
        exclude_str = f" {exclude_flags}" if exclude_flags else ""

        # Show source size (with excludes applied) before running tar
        du_result = _cli.run_command(
            f"{_cli.kubectl_base_cmd()} exec {pod_name} -n {namespace} -c {container_name} "
            f"-- /bin/sh -c 'du -sh{exclude_str} /proc/1/root/{container_path_rel}'",
            check=False,
        )
        if du_result:
            _cli.console.print(
                f"Source size before compression: [info]{escape(du_result.split()[0])}[/]"
            )

        _cli.console.print("[warning]Creating tar.gz archive...[/]")
        backup_cmd = f"tar czf /tmp/kdebug-backup.tar.gz{exclude_str} /proc/1/root/{container_path_rel}"

        cmd = (
            f"{_cli.kubectl_base_cmd()} exec {pod_name} "
            f"-n {namespace} "
            f"-c {container_name} "
            f"-- /bin/bash -c '{backup_cmd}'"
        )

        result = _cli.run_command(cmd, check=True)

        if result is None:
            _cli.err_console.print("[error]✗[/] Backup command failed")
            return False

        _cli.console.print("[success]✓[/] Backup archive created")

        # Show archive size
        size_result = _cli.run_command(
            f"{_cli.kubectl_base_cmd()} exec {pod_name} -n {namespace} -c {container_name} "
            f"-- ls -lh /tmp/kdebug-backup.tar.gz 2>/dev/null | awk '{{print $5}}'",
            check=False,
        )
        if size_result:
            _cli.console.print(
                f"Archive size to download: [info]{escape(size_result.strip())}[/]"
            )

        # Copy backup to local machine
        _cli.console.print("[warning]Copying backup to local machine...[/]")

        cmd = (
            f"{_cli.kubectl_base_cmd()} cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:/tmp/kdebug-backup.tar.gz "
            f"{local_path}"
        )

        result = _cli.run_command(cmd, check=True)

        if result is None:
            _cli.err_console.print("[error]✗[/] Failed to copy backup")
            return False

        _cli.console.print(
            f"[success]✓[/] Backup saved to: [success]{escape(local_path)}[/]"
        )

        # Cleanup remote backup file
        cleanup_cmd = f"{_cli.kubectl_base_cmd()} exec {pod_name} -n {namespace} -c {container_name} -- rm -f /tmp/kdebug-backup.tar.gz"
        _cli.run_command(cleanup_cmd, check=False)

    else:
        # Direct copy without compression
        du_result = _cli.run_command(
            f"{_cli.kubectl_base_cmd()} exec {pod_name} -n {namespace} -c {container_name} "
            f"-- du -sh /proc/1/root{container_path}",
            check=False,
        )
        if du_result:
            _cli.console.print(f"Source size: [info]{escape(du_result.split()[0])}[/]")

        _cli.console.print("[warning]Copying files directly (uncompressed)...[/]")

        cmd = (
            f"{_cli.kubectl_base_cmd()} cp "
            f"-n {namespace} "
            f"-c {container_name} "
            f"{pod_name}:/proc/1/root{container_path} "
            f"{local_path}"
        )

        result = _cli.run_command(cmd, check=False)

        if result is None:
            _cli.err_console.print("[error]✗[/] Failed to copy backup")
            return False

        _cli.console.print(
            f"[success]✓[/] Backup saved to: [success]{escape(local_path)}[/]"
        )

    return True
