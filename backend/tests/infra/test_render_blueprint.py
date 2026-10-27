"""render.yaml: the free-plan Render deployment is wired correctly and would
start in production mode with the values Render asks for."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]

# What a person types into Render for each `sync: false` variable.
TYPED = {
    "DATABASE_URL": (
        "postgresql+asyncpg://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/"
        "postgres?ssl=require"
    ),
    "APP_BASE_URL": "https://mana-career.vercel.app",
    "CORS_ORIGINS": "https://mana-career.vercel.app",
    "SUPABASE_URL": "https://ref.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "LLM_API_KEY": "gsk_groq-key",
    "SMTP_HOST": "smtp.resend.com",
    "SMTP_PORT": "2587",
    "SMTP_USERNAME": "resend",
    "SMTP_PASSWORD": "resend-api-key",
    "EMAIL_FROM_ADDRESS": "hello@mana.example",
}


def _blueprint() -> dict:
    return yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


def _service(kind: str) -> dict:
    return next(s for s in _blueprint()["services"] if s["type"] == kind)


def test_api_runs_free_with_the_worker_inside_and_deploys_after_ci():
    api = _service("web")
    assert api["plan"] == "free" and api["runtime"] == "docker"
    assert api["autoDeployTrigger"] == "checksPass"
    assert api["healthCheckPath"] == "/health"
    assert (ROOT / api["dockerfilePath"]).is_file()
    script = api["dockerCommand"].split()[-1]
    start = (ROOT / "backend" / script).read_text(encoding="utf-8")
    assert "alembic upgrade head" in start and "${PORT" in start and "--workers 1" in start


def test_queue_is_private_and_never_evicts_jobs():
    redis = _service("keyvalue")
    assert redis["ipAllowList"] == []
    assert redis["maxmemoryPolicy"] == "noeviction"
    assert redis["region"] == _service("web")["region"]


def test_secrets_are_typed_into_render_not_committed():
    env = {e["key"]: e for e in _service("web")["envVars"]}
    for key in ("DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SMTP_PASSWORD", "LLM_API_KEY"):
        assert env[key] == {"key": key, "sync": False}
    assert env["JWT_SECRET"].get("generateValue") is True
    assert env["PROXY_SHARED_SECRET"].get("generateValue") is True


def test_the_blueprint_values_pass_production_checks(monkeypatch: pytest.MonkeyPatch):
    values: dict[str, str] = {}
    for item in _service("web")["envVars"]:
        key = item["key"]
        if "value" in item:
            values[key] = str(item["value"])
        elif item.get("generateValue"):
            values[key] = "g" * 44  # Render generates a 256-bit base64 value
        elif "fromService" in item:
            values[key] = "redis://red-abc123:6379"
        else:
            values[key] = TYPED[key]
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.env == "prod" and s.run_worker_in_api and s.file_store == "supabase"
    # The free setup runs a real model (Groq) and real embeddings (on the CPU),
    # as a labelled public demo that forgets its visitors after a week.
    assert (s.llm_provider, s.llm_base_url) == ("openai_compat", "https://api.groq.com/openai/v1")
    assert s.ai_generation_enabled and s.llm_daily_call_limit > 0
    assert (s.embeddings_provider, s.embed_model, s.embed_dim) == (
        "local", "BAAI/bge-small-en-v1.5", 384,
    )
    assert s.demo_mode and s.demo_retention_days == 7
    assert (s.smtp_host, s.smtp_port) == ("smtp-relay.brevo.com", 2525)
    # The demo's agent can only ever email the applicant's own inbox.
    assert s.email_delivery == "redirect"
    assert s.database_pool_size + s.database_max_overflow <= 5


def test_the_embedding_model_is_baked_into_the_image():
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    env = {e["key"]: e.get("value") for e in _service("web")["envVars"]}
    assert f"ARG LOCAL_EMBED_MODEL={env['EMBED_MODEL']}" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
