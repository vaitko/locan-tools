"""Runtime configuration read from environment variables (Lambda env / local .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _secret(name: str) -> str:
    """Env secret; the literal 'disabled' (used by deploy.sh before real keys exist) means not configured."""
    value = os.environ.get(name, "").strip()
    return "" if value.lower() in {"disabled", "-"} else value


DEFAULT_QUOTAS: dict[str, int] = {
    "autocomplete_ip": 300,
    "details_ip": 100,
    "tool_ip": 20,
    "tools_global": 1500,
    "autocomplete_global": 20000,
}


@dataclass(frozen=True)
class Settings:
    env: str = "dev"
    self_hosted: bool = False
    openai_api_key: str = ""
    openai_base_url: str = ""
    replicate_api_token: str = ""
    llm_provider: str = "replicate"  # replicate | openai
    llm_model: str = "openai/gpt-5-nano"
    llm_reasoning_effort: str = "minimal"
    llm_verbosity: str = "low"
    google_places_api_key: str = ""
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:4321"])
    origin_verify_secret: str | None = None
    quota_table: str | None = None
    alert_email: str = ""
    alert_from: str = ""
    site_url: str = "https://locan.ai"
    api_base_url: str = "https://api.locan.ai/api"
    unsubscribe_secret: str = "dev-unsubscribe-secret"
    notify_events: list[str] = field(
        default_factory=lambda: ["tool_run", "error", "quota", "subscribe", "confirm", "unsubscribe", "tool_request"]
    )
    aws_region: str = "us-west-2"
    quota_limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_QUOTAS))
    upstream_timeout_s: float = 25.0

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @classmethod
    def from_env(cls) -> "Settings":
        limits = dict(DEFAULT_QUOTAS)
        for key in limits:
            raw = os.environ.get(f"QUOTA_{key.upper()}")
            if raw and raw.isdigit():
                limits[key] = int(raw)
        self_hosted = os.environ.get("SELF_HOSTED", "").strip().lower() in {"1", "true", "yes", "on"}
        raw_origins = os.environ.get("ALLOWED_ORIGINS")
        if self_hosted and not (raw_origins or "").strip():
            allowed_origins = ["*"]
        elif raw_origins is not None:
            allowed_origins = _csv(raw_origins)
        else:
            allowed_origins = ["http://localhost:4321", "http://localhost:4322"]
        return cls(
            env=os.environ.get("APP_ENV", "dev"),
            self_hosted=self_hosted,
            openai_api_key=_secret("OPENAI_API_KEY"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/"),
            replicate_api_token=_secret("REPLICATE_API_TOKEN"),
            llm_provider=os.environ.get("LLM_PROVIDER", "replicate").strip().lower(),
            llm_model=os.environ.get("LLM_MODEL", "openai/gpt-5-nano").strip(),
            llm_reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "minimal").strip(),
            llm_verbosity=os.environ.get("LLM_VERBOSITY", "low").strip(),
            google_places_api_key=_secret("GOOGLE_PLACES_API_KEY"),
            allowed_origins=allowed_origins,
            origin_verify_secret=os.environ.get("ORIGIN_VERIFY_SECRET") or None,
            quota_table=os.environ.get("QUOTA_TABLE") or None,
            alert_email=os.environ.get("ALERT_EMAIL", "").strip(),
            alert_from=os.environ.get("ALERT_FROM", "").strip(),
            site_url=os.environ.get("SITE_URL", "https://locan.ai").strip().rstrip("/"),
            api_base_url=os.environ.get("API_BASE_URL", "https://api.locan.ai/api").strip().rstrip("/"),
            unsubscribe_secret=os.environ.get("UNSUBSCRIBE_SECRET") or os.environ.get("ORIGIN_VERIFY_SECRET") or "dev-unsubscribe-secret",
            notify_events=_csv(os.environ.get("NOTIFY_EVENTS", "tool_run,error,quota,subscribe,confirm,unsubscribe,tool_request")),
            aws_region=os.environ.get("AWS_REGION", "us-west-2"),
            quota_limits=limits,
            upstream_timeout_s=float(os.environ.get("UPSTREAM_TIMEOUT_S", "25")),
        )
