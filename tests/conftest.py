from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neobank.api import create_app
from neobank.config import Settings
from neobank.db import Database
from neobank.ml.train import train_all


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory) -> Path:
    """Train once per test session and reuse the artifacts everywhere."""
    path = tmp_path_factory.mktemp("models")
    train_all(path)
    return path


@pytest.fixture
def settings(model_dir) -> Settings:
    return Settings(database_url="sqlite://", model_dir=model_dir, allow_synthetic_models=False)


@pytest.fixture
def database() -> Database:
    return Database("sqlite://")


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
