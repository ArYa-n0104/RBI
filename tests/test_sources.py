from __future__ import annotations

import json
from pathlib import Path

import pytest

from taarr.sources import (
    SafeRedirectHandler,
    fetch_source,
    is_official_https_url,
    load_source_register,
    validate_official_url,
)


class FakeHeaders(dict):
    def get_content_type(self):
        return self.get("Content-Type", "application/octet-stream").split(";", 1)[0]


class FakeResponse:
    def __init__(self, content: bytes, url: str, content_type: str = "text/html"):
        self._content = content
        self._position = 0
        self._url = url
        self.headers = FakeHeaders({"Content-Type": content_type, "Content-Length": str(len(content))})

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if size < 0:
            size = len(self._content)
        result = self._content[self._position:self._position + size]
        self._position += len(result)
        return result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout=0):
        del request, timeout
        return self.response


def sample_record():
    return {
        "source_id": "RBI-KYC-TEST",
        "official_url": "https://www.rbi.org.in/example.html",
        "instrument_title": "Synthetic source-register fixture",
    }


def test_official_url_allowlist_accepts_rbi_sebi_and_subdomains():
    assert is_official_https_url("https://www.rbi.org.in/example")
    assert is_official_https_url("https://www.sebi.gov.in/example")
    assert is_official_https_url("https://systemhealth.rbi.org.in/example")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.rbi.org.in/example",
        "https://rbi.org.in.attacker.invalid/example",
        "https://example.org/rbi.org.in",
        "file:///etc/passwd",
        "https://rbi.org.in.example.org/",
    ],
)
def test_official_url_allowlist_rejects_unsafe_urls(url):
    assert not is_official_https_url(url)
    with pytest.raises(ValueError):
        validate_official_url(url)


def test_redirect_handler_rejects_non_official_host():
    from urllib.request import Request

    handler = SafeRedirectHandler()
    req = Request("https://rbi.org.in/start")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {}, "https://example.org/final")


def test_source_register_rejects_duplicate_source_ids(tmp_path: Path):
    path = tmp_path / "sources.csv"
    path.write_text(
        "source_id,official_url\n"
        "ONE,https://rbi.org.in/one\n"
        "ONE,https://sebi.gov.in/two\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate source_id"):
        load_source_register(path)


def test_fetch_source_writes_hash_and_manifest(tmp_path: Path):
    payload = b"<html><body><p>Official source fixture</p></body></html>"
    response = FakeResponse(payload, "https://www.rbi.org.in/example.html")
    entry = fetch_source(
        sample_record(),
        output_root=tmp_path / "raw",
        manifest_path=tmp_path / "manifest.jsonl",
        opener=FakeOpener(response),
    )
    saved = Path(entry["local_path"])
    assert saved.is_file()
    assert saved.read_bytes() == payload
    assert len(entry["sha256"]) == 64
    manifest_lines = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 1
    assert json.loads(manifest_lines[0])["sha256"] == entry["sha256"]


def test_fetch_source_enforces_size_limit_and_cleans_temp_files(tmp_path: Path):
    payload = b"x" * 20
    response = FakeResponse(payload, "https://www.rbi.org.in/example.html")
    with pytest.raises(ValueError, match="exceeding limit"):
        fetch_source(
            sample_record(),
            output_root=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.jsonl",
            max_bytes=10,
            opener=FakeOpener(response),
        )
    assert not list((tmp_path / "raw" / "RBI-KYC-TEST").glob("*.html"))
    assert not (tmp_path / "manifest.jsonl").exists()
