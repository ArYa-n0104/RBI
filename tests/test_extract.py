from __future__ import annotations

from pathlib import Path

from taarr.extract import extract_html_text, extract_text


def test_html_extraction_preserves_headings_and_paragraphs_and_skips_nav():
    html = """
    <!doctype html>
    <html><head><title>Test</title><style>.x { display: none }</style></head>
    <body>
      <nav><p>Ignore navigation</p></nav>
      <main><h1>Chapter I</h1><p>Paragraph 1. First sentence.</p>
      <p>Paragraph 2. Second sentence.</p><script>ignore_me()</script></main>
    </body></html>
    """
    text = extract_html_text(html)
    assert "Chapter I" in text
    assert "Paragraph 1. First sentence." in text
    assert "Paragraph 2. Second sentence." in text
    assert "Ignore navigation" not in text
    assert "ignore_me" not in text


def test_extract_text_reads_html_file(tmp_path: Path):
    path = tmp_path / "source.html"
    path.write_text("<html><body><p>Clause 38(e)</p></body></html>", encoding="utf-8")
    assert extract_text(path) == "Clause 38(e)"


def test_extract_text_reads_text_file(tmp_path: Path):
    path = tmp_path / "source.txt"
    path.write_text("  clause text  \n", encoding="utf-8")
    assert extract_text(path) == "clause text"
