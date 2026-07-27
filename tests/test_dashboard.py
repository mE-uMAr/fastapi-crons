"""Tests for the bundled web dashboard."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_crons import Crons, get_cron_router
from fastapi_crons.dashboard import (
    DASHBOARD_MISSING_HINT,
    get_dashboard_html_path,
    is_dashboard_available,
)


@pytest.fixture
def client():
    app = FastAPI()
    Crons(app)
    app.include_router(get_cron_router(), prefix="/api")
    return TestClient(app)


class TestDashboardBundled:
    """The bundle ships inside the package and must be present."""

    def test_bundle_is_available(self):
        assert is_dashboard_available() is True

    def test_path_points_at_a_real_file(self):
        path = get_dashboard_html_path()
        assert path.is_file()
        assert path.name == "dashboard.html"

    def test_bundle_lives_inside_the_package(self):
        """Guards against the bundle drifting back out of the package."""
        import fastapi_crons

        package_dir = next(iter(fastapi_crons.__path__))
        assert get_dashboard_html_path().parent == type(get_dashboard_html_path())(package_dir)

    def test_route_serves_html(self, client):
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<!doctype html>" in response.text[:200].lower()


class TestDashboardMissing:
    """A build without package data must fail loudly, not silently 500."""

    def test_get_path_raises_with_reinstall_hint(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "fastapi_crons.dashboard.DASHBOARD_HTML", tmp_path / "dashboard.html"
        )
        with pytest.raises(FileNotFoundError, match="force-reinstall"):
            get_dashboard_html_path()

    def test_route_reports_the_problem(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "fastapi_crons.dashboard.DASHBOARD_HTML", tmp_path / "dashboard.html"
        )
        response = client.get("/api/dashboard")
        assert response.status_code == 500
        assert "force-reinstall" in response.json()["detail"]

    def test_other_routes_are_unaffected(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "fastapi_crons.dashboard.DASHBOARD_HTML", tmp_path / "dashboard.html"
        )
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/").status_code == 200


def test_missing_hint_tells_you_what_to_do():
    assert "reinstall" in DASHBOARD_MISSING_HINT.lower()
