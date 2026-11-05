"""Configuration read from environment variables. See .env.example for the full list."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _on_vercel() -> bool:
    return bool(os.getenv("VERCEL"))


def _split_csv(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///neobank.db"
    model_dir: Path = ROOT / "models"
    api_key: str | None = None
    cors_origins: tuple[str, ...] = ()
    # When False, the API refuses to train substitute models on the fly.
    # Set this to False in production and ship trained artifacts instead.
    allow_synthetic_models: bool = True
    fraud_review_threshold: float = 0.30
    fraud_decline_threshold: float = 0.70
    credit_approve_below_pd: float = 0.05
    credit_decline_above_pd: float = 0.15

    @classmethod
    def from_env(cls) -> "Settings":
        # Vercel's filesystem is read-only except /tmp, and /tmp is wiped between
        # cold starts. Set DATABASE_URL to a hosted Postgres for real deployments.
        if _on_vercel():
            default_db = "sqlite:////tmp/neobank.db"
            default_models = Path("/tmp/neobank-models")
        else:
            default_db = f"sqlite:///{ROOT / 'neobank.db'}"
            default_models = ROOT / "models"

        return cls(
            database_url=os.getenv("DATABASE_URL", default_db),
            model_dir=Path(os.getenv("MODEL_DIR", str(default_models))),
            api_key=os.getenv("API_KEY") or None,
            cors_origins=_split_csv(os.getenv("CORS_ORIGINS")),
            allow_synthetic_models=_bool(os.getenv("ALLOW_SYNTHETIC_MODELS"), True),
            fraud_review_threshold=float(os.getenv("FRAUD_REVIEW_THRESHOLD", "0.30")),
            fraud_decline_threshold=float(os.getenv("FRAUD_DECLINE_THRESHOLD", "0.70")),
            credit_approve_below_pd=float(os.getenv("CREDIT_APPROVE_BELOW_PD", "0.05")),
            credit_decline_above_pd=float(os.getenv("CREDIT_DECLINE_ABOVE_PD", "0.15")),
        )
