"""Optional web dashboard support.

The compiled dashboard bundle lives in the separate ``fastapi-crons-dashboard``
distribution so it is only downloaded when explicitly asked for. Nothing here
imports it at module scope -- the lookup happens per request so that a base
install can still import and serve the rest of the router.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD_INSTALL_HINT = (
    "The fastapi-crons dashboard is not installed.\n"
    "Install with: pip install fastapi-crons[dashboard]"
)

__all__ = ["DASHBOARD_INSTALL_HINT", "get_dashboard_html_path", "is_dashboard_installed"]


def get_dashboard_html_path() -> Path:
    """Return the path to the prebuilt dashboard bundle.

    Raises:
        ImportError: If the ``fastapi-crons-dashboard`` package is not installed.
        FileNotFoundError: If it is installed but its bundle is missing.
    """
    try:
        from fastapi_crons_dashboard import get_dashboard_html_path as _resolve
    except ImportError as e:
        raise ImportError(DASHBOARD_INSTALL_HINT) from e

    return _resolve()


def is_dashboard_installed() -> bool:
    """Return whether the dashboard bundle is available to serve."""
    try:
        get_dashboard_html_path()
    except (ImportError, FileNotFoundError):
        return False
    return True
