"""Extract reviewable text from HTML/PDF source snapshots.

Extraction preserves page/section order where possible; it does not infer clause
boundaries or adjudicate legal meaning. Human review remains mandatory.
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar


class _StructuredHTMLText(HTMLParser):
    """Simple structure-aware HTML text extractor without retaining page chrome."""

    _skip_tags: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "svg", "nav", "header", "footer"}
    )
    _block_tags: ClassVar[frozenset[str]] = frozenset(
        {
            "article", "section", "h1", "h2", "h3", "h4", "h5", "p",
            "li", "tr", "td", "th", "br", "main",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._current: list[str] = []
        self.lines: list[str] = []

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._current)).strip()
        if text and (not self.lines or self.lines[-1] != text):
            self.lines.append(text)
        self._current.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if self._skip_stack:
            if normalized in self._skip_tags:
                self._skip_stack.append(normalized)
            return
        if normalized in self._skip_tags:
            self._flush()
            self._skip_stack.append(normalized)
            return
        if normalized in self._block_tags:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if self._skip_stack:
            if normalized == self._skip_stack[-1]:
                self._skip_stack.pop()
            elif normalized in self._skip_stack:
                while self._skip_stack:
                    popped = self._skip_stack.pop()
                    if popped == normalized:
                        break
            return
        if normalized in self._block_tags:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            self._current.append(data)

    def get_text(self) -> str:
        self._flush()
        return "\n".join(self.lines).strip()


def extract_html_text(content: str) -> str:
    parser = _StructuredHTMLText()
    parser.feed(content)
    parser.close()
    return parser.get_text()


def _extract_pdf_text(path: Path) -> str:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires PyMuPDF. Install it with: pip install -e '.[dev,ingest]'"
        ) from exc

    sections: list[str] = []
    document = pymupdf.open(str(path))
    try:
        if document.is_encrypted:
            raise ValueError(f"PDF is encrypted and was not extracted: {path}")
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text").strip()
            sections.append(f"[PAGE {page_number}]\n{page_text}")
    finally:
        document.close()
    return "\n\n".join(sections).strip()


def extract_text(path: str | Path) -> str:
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source snapshot not found: {source_path}")
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(source_path)
    if suffix in {".html", ".htm", ".xhtml"}:
        return extract_html_text(source_path.read_text(encoding="utf-8", errors="replace"))
    if suffix in {".txt", ".md"}:
        return source_path.read_text(encoding="utf-8", errors="replace").strip()

    # Detect common file signatures before falling back to UTF-8 text.
    with source_path.open("rb") as handle:
        signature = handle.read(5)
    if signature.startswith(b"%PDF-"):
        return _extract_pdf_text(source_path)
    raw = source_path.read_text(encoding="utf-8", errors="replace")
    if "<html" in raw[:2000].lower() or "<!doctype html" in raw[:2000].lower():
        return extract_html_text(raw)
    return raw.strip()


def write_extraction(source_path: Path, output_path: Path) -> int:
    text = extract_text(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return len(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract text for human review from source snapshots.")
    parser.add_argument("source", help="path to a local HTML, PDF, text or Markdown file")
    parser.add_argument("--output", help="output text path; omit to print to stdout")
    args = parser.parse_args(argv)

    try:
        source_path = Path(args.source)
        if args.output:
            character_count = write_extraction(source_path, Path(args.output))
            print(f"Extracted {character_count} characters to {args.output}")
        else:
            print(extract_text(source_path))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
