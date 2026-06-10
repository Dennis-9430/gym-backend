"""Tests for devops infrastructure — Docker, CI, health/ready endpoints."""
import asyncio
from pathlib import Path

import pytest


class TestDockerfile:
    """Dockerfile structure and configuration."""

    def test_dockerfile_exists(self):
        """Dockerfile exists in project root."""
        assert Path("Dockerfile").exists(), "Dockerfile must exist in project root"

    def test_dockerfile_multi_stage_build(self):
        """Dockerfile uses multi-stage build with builder and production stages."""
        content = Path("Dockerfile").read_text()
        assert "AS builder" in content
        assert "AS production" in content

    def test_dockerfile_python_312(self):
        """Dockerfile uses Python 3.12-slim."""
        content = Path("Dockerfile").read_text()
        assert "python:3.12-slim" in content

    def test_dockerfile_healthcheck(self):
        """Dockerfile has HEALTHCHECK instruction."""
        content = Path("Dockerfile").read_text()
        assert "HEALTHCHECK" in content

    def test_dockerfile_exposes_port_8000(self):
        """Dockerfile exposes port 8000."""
        content = Path("Dockerfile").read_text()
        assert "8000" in content

    def test_dockerfile_uvicorn_command(self):
        """Dockerfile CMD uses uvicorn with app.main:app."""
        content = Path("Dockerfile").read_text()
        assert 'CMD ["uvicorn", "app.main:app"' in content


class TestDockerCompose:
    """docker-compose.yml service definitions."""

    def test_docker_compose_exists(self):
        """docker-compose.yml exists in project root."""
        assert Path("docker-compose.yml").exists()

    def test_docker_compose_has_mongodb(self):
        """docker-compose defines mongodb service."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        assert "mongodb" in compose.get("services", {})

    def test_docker_compose_has_redis(self):
        """docker-compose defines redis service."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        assert "redis" in compose.get("services", {})

    def test_docker_compose_has_backend(self):
        """docker-compose defines backend service."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        assert "backend" in compose.get("services", {})

    def test_docker_compose_backend_depends_on_mongodb_healthy(self):
        """Backend service depends on healthy mongodb."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        deps = compose["services"]["backend"].get("depends_on", {})
        assert deps.get("mongodb", {}).get("condition") == "service_healthy"

    def test_docker_compose_backend_depends_on_redis_healthy(self):
        """Backend service depends on healthy redis."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        deps = compose["services"]["backend"].get("depends_on", {})
        assert deps.get("redis", {}).get("condition") == "service_healthy"

    def test_docker_compose_mongodb_image(self):
        """MongoDB uses mongo:7 image."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        assert compose["services"]["mongodb"]["image"] == "mongo:7"

    def test_docker_compose_redis_image(self):
        """Redis uses redis:7-alpine image."""
        import yaml
        compose = yaml.safe_load(Path("docker-compose.yml").read_text())
        assert compose["services"]["redis"]["image"] == "redis:7-alpine"


class TestDockerignore:
    """.dockerignore configuration."""

    def test_dockerignore_exists(self):
        """.dockerignore exists in project root."""
        assert Path(".dockerignore").exists()

    def test_dockerignore_has_entries(self):
        """.dockerignore is non-empty."""
        assert len(Path(".dockerignore").read_text().strip()) > 0

    def test_dockerignore_excludes_pycache(self):
        """.dockerignore excludes __pycache__."""
        assert "__pycache__" in Path(".dockerignore").read_text()

    def test_dockerignore_excludes_env(self):
        """.dockerignore excludes .env files."""
        assert ".env" in Path(".dockerignore").read_text()

    def test_dockerignore_excludes_git(self):
        """.dockerignore excludes .git."""
        assert ".git" in Path(".dockerignore").read_text()


class TestCIWorkflow:
    """GitHub Actions CI workflow."""

    def test_ci_workflow_exists(self):
        """CI workflow file exists."""
        assert Path(".github/workflows/ci.yml").exists()

    def test_ci_workflow_has_lint_job(self):
        """CI workflow has a lint job."""
        import yaml
        ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
        assert "lint" in ci.get("jobs", {})

    def test_ci_workflow_has_test_job(self):
        """CI workflow has a test job."""
        import yaml
        ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
        assert "test" in ci.get("jobs", {})

    def test_ci_workflow_on_push(self):
        """CI triggers on push to main and feature/fix/security/refactor branches."""
        import yaml
        ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
        push = ci.get("on", {}).get("push", {})
        branches = push.get("branches", [])
        assert "main" in branches
        assert "feature/**" in branches
        assert "fix/**" in branches

    def test_ci_workflow_on_pull_request(self):
        """CI triggers on PR to main."""
        import yaml
        ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
        pr = ci.get("on", {}).get("pull_request", {})
        assert pr.get("branches") == ["main"]


class TestHealthEndpointExistence:
    """Health and readiness endpoint existence checks (sync)."""

    def test_health_endpoint_exists_in_main(self):
        """app/main.py has /health endpoint."""
        content = Path("app/main.py").read_text(encoding="utf-8")
        assert '"/health"' in content or '"/health")' in content

    def test_ready_endpoint_exists_in_main(self):
        """app/main.py has /ready endpoint."""
        content = Path("app/main.py").read_text(encoding="utf-8")
        assert '"/ready"' in content or '"/ready")' in content


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Health and readiness endpoint behavior."""

    async def test_health_endpoint_returns_json(self):
        """Health endpoint response has JSON format."""
        from app.main import app
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"status": "healthy"}

    async def test_ready_endpoint_returns_proper_format(self):
        """Ready endpoint returns JSON with status and mongodb fields."""
        from app.main import app
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/ready")
        data = resp.json()
        assert "status" in data
        assert "mongodb" in data

    async def test_ready_endpoint_returns_503_when_db_not_connected(self):
        """Ready endpoint returns 503 when MongoDB is not connected."""
        from app.main import app
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "not initialized" in data["mongodb"].lower()
