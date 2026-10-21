import pytest


@pytest.fixture(autouse=True)
def _isolate_from_real_env_file(tmp_path, monkeypatch):
    """Never let a test read a developer's real .env (and real Gemini key)."""
    monkeypatch.setenv("TAARR_ENV_FILE", str(tmp_path / "no-such.env"))
