"""Loads model artifacts from disk. Missing artifacts are trained on synthetic data unless disabled."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from .train import TRAINERS

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    name: str
    model: Any
    version: str
    metrics: dict[str, Any]


class ModelRegistry:
    def __init__(self, model_dir: Path, *, allow_synthetic: bool = True) -> None:
        self.model_dir = Path(model_dir)
        self.allow_synthetic = allow_synthetic
        self._loaded: dict[str, LoadedModel] = {}

    def get(self, name: str) -> LoadedModel:
        if name not in self._loaded:
            self._loaded[name] = self._load_or_train(name)
        return self._loaded[name]

    def _load_or_train(self, name: str) -> LoadedModel:
        if name not in TRAINERS:
            raise KeyError(f"unknown model {name!r}")
        path = self.model_dir / f"{name}.joblib"

        if path.exists():
            bundle = joblib.load(path)
        elif not self.allow_synthetic:
            raise RuntimeError(
                f"model artifact {path} not found and synthetic fallback is disabled. "
                "Run `python -m neobank.ml.train` or copy in a trained artifact."
            )
        else:
            log.warning("model artifact %s missing; training on synthetic data", path)
            bundle = TRAINERS[name]()
            try:
                self.model_dir.mkdir(parents=True, exist_ok=True)
                joblib.dump(bundle, path)
            except OSError:
                log.info("model directory is read-only; keeping the model in memory only")

        return LoadedModel(name=name, model=bundle["model"], version=bundle["version"], metrics=bundle["metrics"])
