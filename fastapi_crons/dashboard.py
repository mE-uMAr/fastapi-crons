"""Web dashboard assets.

The compiled bundle ships inside this package (see ``package-data`` in
pyproject.toml). The lookup still goes through here rather than being inlined
into the route so that a bundle missing from a bad build produces a clear
error instead of a bare FileNotFoundError.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"

DASHBOARD_MISSING_HINT = (
    "The fastapi-crons dashboard bundle is missing from this installation.\n"
    "Reinstall with: pip install --force-reinstall fastapi-crons"
)

__all__ = ["DASHBOARD_MISSING_HINT", "get_dashboard_html_path", "is_dashboard_available"]


def get_dashboard_html_path() -> Path:
    """Return the path to the dashboard bundle.

    Raises:
        FileNotFoundError: If the bundle is absent, which means the package was
            built without its package data.
    """
    if not DASHBOARD_HTML.is_file():
        raise FileNotFoundError(DASHBOARD_MISSING_HINT)
    return DASHBOARD_HTML


def is_dashboard_available() -> bool:
    """Return whether the dashboard bundle is present and servable."""
    return DASHBOARD_HTML.is_file()
