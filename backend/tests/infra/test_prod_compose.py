from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _compose_config(
    tmp_path: Path, *, password: str | None, jwt_secret: str | None = "j" * 40
) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is not installed")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    env.pop("PROXY_SUBNET", None)
    env.pop("NGINX_PROXY_IP", None)
    env.pop("PROXY_DYNAMIC_RANGE", None)
    env.pop("JWT_SECRET", None)
    if password is not None:
        env["POSTGRES_PASSWORD"] = password
    if jwt_secret is not None:
        env["JWT_SECRET"] = jwt_secret
    return subprocess.run(  # noqa: S603 - fixed Docker Compose CLI arguments; no shell
        [
            docker,
            "compose",
            "--env-file",
            str(empty_env),
            "-f",
            str(ROOT / "compose.prod.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_prod_compose_requires_postgres_password(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password=None)
    assert result.returncode != 0
    assert "POSTGRES_PASSWORD" in result.stderr


def test_api_and_worker_mount_the_same_persistent_file_directory(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password="test-only-password")
    if result.returncode != 0:
        pytest.skip(f"Docker Compose config unavailable: {result.stderr}")

    services = json.loads(result.stdout)["services"]
    mounts = {}
    for service_name in ("api", "worker"):
        service = services[service_name]
        mounts[service_name] = {
            mount["target"]: mount["source"]
            for mount in service["volumes"]
            if mount["target"] == "/app/var/files"
        }
        assert service["environment"]["FILE_STORE_LOCAL_DIR"] == "/app/var/files"
    assert mounts["api"] == mounts["worker"]
    assert "/app/var/files" in mounts["api"]


def test_file_store_bind_mount_never_creates_an_empty_host_directory() -> None:
    # Checked against the source file: some Compose versions drop
    # `create_host_path` from resolved `config` output.
    source = yaml.safe_load((ROOT / "compose.prod.yml").read_text(encoding="utf-8"))
    for service_name in ("api", "worker"):
        mount = next(
            m
            for m in source["services"][service_name]["volumes"]
            if isinstance(m, dict) and m.get("target") == "/app/var/files"
        )
        assert mount["type"] == "bind"
        assert mount["bind"]["create_host_path"] is False


def test_prod_compose_requires_jwt_secret(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password="test-only-password", jwt_secret=None)
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr


def test_backend_services_always_run_as_production(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password="test-only-password")
    if result.returncode != 0:
        pytest.skip(f"Docker Compose config unavailable: {result.stderr}")
    services = json.loads(result.stdout)["services"]
    for name in ("migrate", "api", "worker"):
        assert services[name]["environment"]["ENV"] == "prod"


def test_prod_compose_limits_forwarded_ip_trust_to_nginx(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password="test-only-password")
    if result.returncode != 0:
        pytest.skip(f"Docker Compose config unavailable: {result.stderr}")

    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services["api"]["networks"]) == {"data", "ingress"}
    assert set(services["db"]["networks"]) == {"data"}
    assert set(services["redis"]["networks"]) == {"data"}
    assert set(services["worker"]["networks"]) == {"data"}
    assert set(services["frontend"]["networks"]) == {"ingress"}
    assert set(services["nginx"]["networks"]) == {"ingress"}
    nginx_network = services["nginx"]["networks"]["ingress"]
    assert nginx_network["ipv4_address"] == "172.30.0.2"
    assert "--forwarded-allow-ips=172.30.0.2" in services["api"]["command"]
    assert "ports" not in services["api"]
    ipam = config["networks"]["ingress"]["ipam"]["config"][0]
    assert ipam["subnet"] == "172.30.0.0/24"
    # The fixed proxy address must be outside the dynamic pool, or Docker can
    # hand it to api/frontend first ("Address already in use" for nginx).
    dynamic = ipaddress.ip_network(ipam["ip_range"])
    assert ipaddress.ip_address(nginx_network["ipv4_address"]) not in dynamic
    assert dynamic.subnet_of(ipaddress.ip_network(ipam["subnet"]))
