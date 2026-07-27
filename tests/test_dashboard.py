"""Tests for the optional dashboard extra."""

import builtins

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_crons import Crons, get_cron_router
from fastapi_crons.dashboard import (
    DASHBOARD_INSTALL_HINT,
    get_dashboard_html_path,
    is_dashboard_installed,
)


@pytest.fixture
def client():
    app = FastAPI()
    Crons(app)
    app.include_router(get_cron_router(), prefix="/api")
    return TestClient(app)


@pytest.fixture
def dashboard_missing(monkeypatch):
    """Simulate a base install without the fastapi-crons-dashboard package."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fastapi_crons_dashboard":
            raise ImportError("No module named 'fastapi_crons_dashboard'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


class TestDashboardNotInstalled:
    """The base install must stay usable without the dashboard bundle."""

    def test_is_dashboard_installed_returns_false(self, dashboard_missing):
        assert is_dashboard_installed() is False

    def test_get_path_raises_with_install_hint(self, dashboard_missing):
        with pytest.raises(ImportError, match=r"fastapi-crons\[dashboard\]"):
            get_dashboard_html_path()

    def test_route_returns_501_with_install_hint(self, client, dashboard_missing):
        response = client.get("/api/dashboard")
        assert response.status_code == 501
        assert "fastapi-crons[dashboard]" in response.json()["detail"]

    def test_other_routes_still_work(self, client, dashboard_missing):
        """A missing dashboard must not break the rest of the router."""
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/").status_code == 200


class TestDashboardInstalled:
    """Behaviour when the optional bundle is present."""

    def test_serves_html(self, client):
        pytest.importorskip("fastapi_crons_dashboard")

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<!doctype html>" in response.text[:200].lower()

    def test_bundle_path_exists(self):
        pytest.importorskip("fastapi_crons_dashboard")

        path = get_dashboard_html_path()
        assert path.is_file()
        assert path.name == "dashboard.html"


def test_install_hint_names_the_extra():
    assert "pip install fastapi-crons[dashboard]" in DASHBOARD_INSTALL_HINT
