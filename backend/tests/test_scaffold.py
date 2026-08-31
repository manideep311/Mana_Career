import importlib
import tomllib
from pathlib import Path


def test_app_package_importable():
    assert importlib.import_module("app") is not None


def test_pyproject_declares_python_312_and_core_deps():
    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.12,<3.13"
    deps = " ".join(data["project"]["dependencies"])
    for pkg in ("fastapi", "sqlalchemy", "alembic", "pydantic-settings",
                "structlog", "arq", "redis", "asyncpg", "argon2-cffi", "pyjwt",
                "pgvector"):
        assert pkg in deps, f"missing dependency: {pkg}"


def test_importlinter_contract_file_present():
    assert (Path(__file__).parents[1] / ".importlinter").exists()
