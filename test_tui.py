#!/usr/bin/env python3
"""
Test script to demonstrate the TUI functionality without requiring a K8s cluster.
This simulates the interactive menu system.
"""

import sys
import termios
import tty

# ANSI Color codes


class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
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


def read_key() -> str:
    """Read a single keypress from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Handle arrow keys (escape sequences)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'up'
                elif ch3 == 'B':
                    return 'down'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def display_menu(title: str, items: list, selected_idx: int, show_numbers: bool = True):
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
                f"{colorize(prefix + number + item, Colors.BOLD + Colors.BRIGHT_GREEN)}")
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
        print(
            f"\n  {colorize('q.', Colors.WHITE)} {colorize('Quit', Colors.CYAN)}")

    # Print instructions
    print(f"\n{colorize('─' * 70, Colors.DIM)}")
    if show_numbers:
        print(
            f"{colorize('Use ↑/↓ arrows or numbers to select, Enter to confirm', Colors.BRIGHT_BLACK)}")
    else:
        print(
            f"{colorize('Use ↑/↓ arrows to select, Enter to confirm', Colors.BRIGHT_BLACK)}")
    print(f"{colorize('─' * 70, Colors.DIM)}\n")


def interactive_menu(title: str, items: list, show_numbers: bool = True):
    """Display an interactive menu and return the selected index."""
    if not items:
        print(f"{colorize('✗ Error:', Colors.RED)} No items to display")
        return None

    selected_idx = 0
    quit_idx = len(items)  # Quit is one position after last item

    while True:
        display_menu(title, items, selected_idx, show_numbers)

        key = read_key()

        if key == 'up':
            selected_idx = (selected_idx - 1) % (len(items) + 1)
        elif key == 'down':
            selected_idx = (selected_idx + 1) % (len(items) + 1)
        elif key == '\r' or key == '\n':  # Enter
            if selected_idx == quit_idx:
                return None  # Quit selected
            return selected_idx
        elif key == 'q' or key == 'Q':
            return None
        elif key.isdigit() and show_numbers:
            num = int(key)
            if 1 <= num <= len(items):
                selected_idx = num - 1
                return selected_idx


def main():
    """Demo the TUI system."""
    print(f"\n{colorize('kdebug TUI Demo - Pod Selection', Colors.BOLD + Colors.BRIGHT_CYAN)}\n")

    # Demo: Pod selection
    pod_items = [
        f"{colorize('frontend-abc123', Colors.CYAN)} ({colorize('Running', Colors.GREEN)})",
        f"{colorize('frontend-def456', Colors.CYAN)} ({colorize('Running', Colors.GREEN)})",
        f"{colorize('backend-ghi789', Colors.CYAN)} ({colorize('Running', Colors.GREEN)})",
        f"{colorize('database-0', Colors.CYAN)} ({colorize('Running', Colors.GREEN)})",
        f"{colorize('worker-jkl012', Colors.CYAN)} ({colorize('Pending', Colors.YELLOW)})",
        f"{colorize('cache-mno345', Colors.CYAN)} ({colorize('Running', Colors.GREEN)})",
    ]

    result = interactive_menu(
        f"Select Pod in namespace: {colorize('production', Colors.MAGENTA)}",
        pod_items
    )

    if result is not None:
        pods = ['frontend-abc123', 'frontend-def456', 'backend-ghi789',
                'database-0', 'worker-jkl012', 'cache-mno345']
        print(f"\n{colorize('✓ Selected pod:', Colors.GREEN)} {pods[result]}")
        print(
            f"{colorize('Next step:', Colors.CYAN)} Launch debug container in {colorize(pods[result], Colors.BRIGHT_CYAN)}")
    else:
        print(f"\n{colorize('Selection cancelled', Colors.YELLOW)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{colorize('Interrupted by user', Colors.YELLOW)}")
        sys.exit(0)

# Made with Bob
