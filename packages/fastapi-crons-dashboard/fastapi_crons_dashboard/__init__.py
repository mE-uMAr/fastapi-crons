"""Prebuilt web dashboard assets for fastapi-crons.

This distribution carries nothing but the compiled single-file dashboard
bundle. It is kept separate from ``fastapi-crons`` so the base install stays
small; ``fastapi_crons`` reaches for it only when the dashboard route is hit.
"""

from pathlib import Path

__version__ = "0.1.0"
__all__ = ["get_dashboard_html_path"]

_DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"


def get_dashboard_html_path() -> Path:
    """Return the path to the prebuilt dashboard bundle.

    Raises:
        FileNotFoundError: If the bundle is missing from the installation,
            which means the distribution was built without its package data.
    """
    if not _DASHBOARD_HTML.is_file():
        raise FileNotFoundError(
            f"dashboard.html is missing from the fastapi-crons-dashboard "
            f"installation at {_DASHBOARD_HTML}. Try reinstalling with: "
            f"pip install --force-reinstall fastapi-crons-dashboard"
        )
    return _DASHBOARD_HTML
