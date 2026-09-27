from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _compose_config(tmp_path: Path, *, password: str | None) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is not installed")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    if password is not None:
        env["POSTGRES_PASSWORD"] = password
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
