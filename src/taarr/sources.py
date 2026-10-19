"""Safe acquisition of source pages from the TAARR official-source register.

Raw source snapshots are written under data/raw/ (git-ignored); only provenance
metadata is written to the acquisition manifest. Downloads are limited to official
RBI/SEBI domains and redirects to other hosts are rejected.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

OFFICIAL_DOMAINS = ("rbi.org.in", "sebi.gov.in")
SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CHUNK_SIZE = 64 * 1024


def is_official_https_url(url: str) -> bool:
    """Return True for HTTPS URLs on RBI/SEBI domains or their subdomains."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(host)
        and any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)
    )


def validate_official_url(url: str) -> None:
    if not is_official_https_url(url):
        raise ValueError(
            "Source URL must use HTTPS and be hosted on rbi.org.in or sebi.gov.in "
            "(including official subdomains). Review any third-party redirect manually."
        )


class SafeRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that leave the official RBI/SEBI domain allowlist."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute_url = urljoin(req.full_url, newurl)
        validate_official_url(absolute_url)
        return super().redirect_request(req, fp, code, msg, headers, absolute_url)


def load_source_register(path: str | Path) -> list[dict[str, str]]:
    """Load source records and reject missing columns, IDs, URLs, or duplicate IDs."""
    register_path = Path(path)
    if not register_path.is_file():
        raise FileNotFoundError(f"Source register not found: {register_path}")

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    with register_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"source_id", "official_url"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Source register requires source_id and official_url columns")
        for line_number, row in enumerate(reader, start=2):
            source_id = (row.get("source_id") or "").strip()
            url = (row.get("official_url") or "").strip()
            if not source_id or not SOURCE_ID_PATTERN.fullmatch(source_id):
                raise ValueError(f"Invalid source_id at CSV line {line_number}")
            if source_id in seen:
                raise ValueError(f"Duplicate source_id {source_id!r} at CSV line {line_number}")
            validate_official_url(url)
            seen.add(source_id)
            records.append({key: (value or "").strip() for key, value in row.items() if key})
    return records


def _extension_for(content_type: str, final_url: str) -> str:
    normalized = content_type.lower().split(";", 1)[0].strip()
    suffix = Path(urlparse(final_url).path).suffix.lower()
    if normalized == "application/pdf" or suffix == ".pdf":
        return ".pdf"
    if normalized in {"text/html", "application/xhtml+xml"} or suffix in {".html", ".htm"}:
        return ".html"
    if normalized.startswith("text/") or normalized in {"application/xml", "text/xml"}:
        return ".txt"
    return ".bin"


def fetch_source(
    record: dict[str, str],
    output_root: str | Path = "data/raw",
    manifest_path: str | Path = "data/source_acquisition_manifest.jsonl",
    timeout: float = 25.0,
    max_bytes: int = 40 * 1024 * 1024,
    opener: Any = None,
) -> dict[str, Any]:
    """Fetch one official source record, save a local snapshot, and append provenance."""
    source_id = (record.get("source_id") or "").strip()
    source_url = (record.get("official_url") or "").strip()
    if not source_id or not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError("Source record has an invalid or missing source_id")
    validate_official_url(source_url)
    if timeout <= 0 or max_bytes <= 0:
        raise ValueError("timeout and max_bytes must be positive")

    safe_opener = opener if opener is not None else build_opener(SafeRedirectHandler())
    request = Request(
        source_url,
        headers={
            "User-Agent": "TAARR-Research-Prototype/0.1 (official-source acquisition)",
            "Accept": "text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )

    source_dir = Path(output_root) / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        response_context = safe_opener.open(request, timeout=timeout)
        with response_context as response:
            final_url = response.geturl()
            validate_official_url(final_url)
            headers = response.headers
            try:
                content_length = int(headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                content_length = 0
            if content_length > max_bytes:
                raise ValueError(
                    f"Source advertises {content_length} bytes, exceeding limit {max_bytes}"
                )
            content_type = (
                headers.get_content_type()
                if hasattr(headers, "get_content_type")
                else headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
            )

            digest = hashlib.sha256()
            size_bytes = 0
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".taarr-download-", dir=source_dir, delete=False
            ) as temp_handle:
                temp_path = Path(temp_handle.name)
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise ValueError(f"Source exceeds the {max_bytes}-byte download limit")
                    digest.update(chunk)
                    temp_handle.write(chunk)

        sha256 = digest.hexdigest()
        extension = _extension_for(content_type, final_url)
        destination = source_dir / f"{sha256[:16]}{extension}"
        if destination.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(destination)
        temp_path = None

        try:
            local_relative_path = destination.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            local_relative_path = destination.resolve().as_posix()

        entry: dict[str, Any] = {
            "source_id": source_id,
            "requested_url": source_url,
            "final_url": final_url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "local_path": local_relative_path,
        }
        manifest = Path(manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("a", encoding="utf-8") as manifest_handle:
            manifest_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire official TAARR RBI/SEBI source snapshots.")
    parser.add_argument(
        "--register", default="data/sources/source_register.csv",
        help="CSV source register path",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list source IDs and official URLs")
    fetch_parser = subparsers.add_parser("fetch", help="fetch selected source records")
    fetch_parser.add_argument("source_ids", nargs="+", help="one or more source IDs from the CSV")
    fetch_parser.add_argument("--output-root", default="data/raw", help="local raw snapshot directory")
    fetch_parser.add_argument(
        "--manifest", default="data/source_acquisition_manifest.jsonl",
        help="local provenance manifest path",
    )
    fetch_parser.add_argument("--timeout", type=float, default=25.0)
    fetch_parser.add_argument("--max-mb", type=int, default=40)

    args = parser.parse_args(argv)
    try:
        records = load_source_register(args.register)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        for record in records:
            print(f"{record['source_id']}\t{record['official_url']}")
        return 0

    index = {record["source_id"]: record for record in records}
    requested = args.source_ids
    unknown = [source_id for source_id in requested if source_id not in index]
    if unknown:
        print(f"ERROR: unknown source ID(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    failed = False
    for source_id in requested:
        try:
            entry = fetch_source(
                index[source_id],
                output_root=args.output_root,
                manifest_path=args.manifest,
                timeout=args.timeout,
                max_bytes=args.max_mb * 1024 * 1024,
            )
        except Exception as exc:  # CLI should report per-source network/format failures.
            failed = True
            print(f"FAILED {source_id}: {exc}", file=sys.stderr)
        else:
            print(
                f"OK {source_id}: {entry['local_path']} "
                f"(sha256={entry['sha256']}, bytes={entry['size_bytes']})"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
