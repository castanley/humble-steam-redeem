"""Shared utilities: prompts, cookie management, session verification, helpers."""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path
from typing import Any, Generator, Union

# Rich renders status symbols that aren't representable in the Windows
# console's legacy code pages. Configure streams before creating the Console.
if os.name == "nt":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from src import APP_NAME, __version__

# Shared console instance — single source of truth for all output
console = Console()

# Humble / Steam page URLs used for session verification
HUMBLE_KEYS_PAGE = "https://www.humblebundle.com/home/library"
STEAM_KEYS_PAGE = "https://store.steampowered.com/account/registerkey"


# ---------------------------------------------------------------------------
# Non-UI helpers
# ---------------------------------------------------------------------------

def find_dict_keys(
    node: Any, kv: str, parent: bool = False
) -> Generator[Any, None, None]:
    """Recursively traverse nested dicts/lists yielding values (or parent dicts) for *kv*."""
    if isinstance(node, list):
        for item in node:
            yield from find_dict_keys(item, kv, parent)
    elif isinstance(node, dict):
        if kv in node:
            yield node if parent else node[kv]
        for value in node.values():
            yield from find_dict_keys(value, kv, parent)


def try_recover_cookies(cookie_file: Union[str, Path], session) -> bool:
    """Load pickled cookies into *session*. Returns True on success."""
    try:
        with open(cookie_file, "rb") as f:
            session.cookies.update(pickle.load(f))
        return True
    except Exception:
        return False


def export_cookies(cookie_file: Union[str, Path], session) -> bool:
    """Persist *session* cookies to *cookie_file*. Returns True on success."""
    try:
        with open(cookie_file, "wb") as f:
            pickle.dump(session.cookies, f)
        return True
    except Exception:
        return False


def verify_logins_session(session) -> list[bool]:
    """Return ``[humble_logged_in, steam_logged_in]`` for *session*."""
    results: list[bool] = []
    for url in [HUMBLE_KEYS_PAGE, STEAM_KEYS_PAGE]:
        r = session.get(url, allow_redirects=False)
        results.append(r.status_code not in (301, 302))
    return results


def valid_steam_key(key: str | None) -> bool:
    """Check whether *key* looks like a Steam key (XXXXX-XXXXX-XXXXX)."""
    if not isinstance(key, str):
        return False
    parts = key.split("-")
    return len(key) == 17 and len(parts) == 3 and all(len(p) == 5 for p in parts)


# ---------------------------------------------------------------------------
# TUI primitives
# ---------------------------------------------------------------------------

def cls() -> None:
    """Clear the terminal and print the branded header."""
    os.system("cls" if os.name == "nt" else "clear")
    print_header()


def print_header() -> None:
    """Print the application header — double-line box, centered, with version."""
    console.print()
    console.print(
        Panel(
            f"[bold cyan]-= {APP_NAME} =-[/bold cyan]\n"
            f"[dim]v{__version__}[/dim]",
            box=box.DOUBLE,
            border_style="bright_blue",
            expand=False,
            padding=(1, 4),
        ),
        justify="center",
    )
    console.print()


def print_rule(title: str = "", style: str = "bright_blue") -> None:
    """Print a horizontal rule, optionally with a centered title."""
    console.print()
    if title:
        console.print(Rule(title, style=style))
    else:
        console.print(Rule(style="dim"))


def print_success(msg: str) -> None:
    """Print a success message with ✓ prefix."""
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_error(msg: str) -> None:
    """Print an error message with ✗ prefix."""
    console.print(f"[bold red]✗[/bold red] [red]{msg}[/red]")


def print_warning(msg: str) -> None:
    """Print a warning message with ⚠ prefix."""
    console.print(f"[bold yellow]⚠[/bold yellow] [yellow]{msg}[/yellow]")


def print_info(msg: str) -> None:
    """Print an informational message with › prefix."""
    console.print(f"[dim]›[/dim] {msg}")


# ---------------------------------------------------------------------------
# Interactive prompts (single-keypress + arrow-key navigation)
# ---------------------------------------------------------------------------

# ANSI escape helpers
_CLR = "\033[2K\r"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RST = "\033[0m"


def _read_key() -> str:
    """Read a single keypress. Returns 'up'/'down'/'left'/'right' for arrows."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(ch2, "")
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(ch3, "")
            return ""
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def prompt_menu(options: list[str], shortcuts: list[str] | None = None) -> int:
    """Vertical menu with arrow-key navigation and instant shortcut keys.

    Returns the index of the selected option.
    """
    n = len(options)
    if shortcuts is None:
        shortcuts = [str(i + 1) for i in range(n)]
    selected = 0

    # Initial draw
    for i in range(n):
        _draw_menu_line(options[i], shortcuts[i], i == selected)

    while True:
        key = _read_key()
        if key == "up" and selected > 0:
            selected -= 1
        elif key == "down" and selected < n - 1:
            selected += 1
        elif key in ("\r", "\n"):
            sys.stdout.flush()
            return selected
        elif key == "\x03":
            sys.stdout.flush()
            raise KeyboardInterrupt
        else:
            # Instant shortcut key
            for i, sc in enumerate(shortcuts):
                if key.lower() == sc.lower():
                    sys.stdout.flush()
                    return i
            continue

        # Redraw in place
        sys.stdout.write(f"\033[{n}A")
        for i in range(n):
            _draw_menu_line(options[i], shortcuts[i], i == selected)


def _draw_menu_line(label: str, shortcut: str, selected: bool) -> None:
    """Render a single menu line in place."""
    sys.stdout.write(_CLR)
    if selected:
        sys.stdout.write(f"{_BOLD}{_CYAN}› {shortcut}  ·  {label}{_RST}\n")
    else:
        sys.stdout.write(f"  {_DIM}{shortcut}  ·  {label}{_RST}\n")
    sys.stdout.flush()


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Inline y/n toggle with arrow keys. Press y/n or arrows + Enter."""
    selected = default
    _draw_yn(question, selected)

    while True:
        key = _read_key()
        if key in ("left", "right", "up", "down"):
            selected = not selected
            _draw_yn(question, selected)
        elif key in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return selected
        elif key.lower() == "y":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return True
        elif key.lower() == "n":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return False
        elif key == "\x03":
            sys.stdout.write("\n")
            sys.stdout.flush()
            raise KeyboardInterrupt


def _draw_yn(question: str, selected: bool) -> None:
    """Render the inline yes/no toggle."""
    sys.stdout.write(_CLR)
    if selected:
        yes = f"{_BOLD}{_CYAN}‹ Yes ›{_RST}"
        no = f"{_DIM}  No  {_RST}"
    else:
        yes = f"{_DIM}  Yes  {_RST}"
        no = f"{_BOLD}{_CYAN}‹ No  ›{_RST}"
    sys.stdout.write(f"{question}  {yes} {no}")
    sys.stdout.flush()


def write_skipped(skipped_games: dict[str, dict]) -> None:
    """Write skipped games to file and inform the user."""
    with open("skipped.txt", "w", encoding="utf-8-sig") as f:
        for name in skipped_games:
            f.write(name + "\n")

    print_info(
        f"Skipped [bold]{len(skipped_games)}[/bold] games we think you already own."
    )
    print_info(
        "Written to [cyan]skipped.txt[/cyan] — edit that file and rerun to retry them."
    )
