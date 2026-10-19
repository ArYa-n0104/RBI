from __future__ import annotations

import json

from taarr.annotation import agreement_report, load_items


def item(first: str | None, second: str | None, item_id: str = "TEST-1"):
    annotations = {}
    if first is not None:
        annotations["annotator_1"] = {"outcome": first}
    if second is not None:
        annotations["annotator_2"] = {"outcome": second}
    return {"benchmark_item_id": item_id, "annotations": annotations}


def test_agreement_report_computes_perfect_agreement():
    report = agreement_report([
        item("Applicable", "Applicable", "1"),
        item("Indeterminate", "Indeterminate", "2"),
    ])
    assert report["n_paired"] == 2
    assert report["n_excluded"] == 0
    assert report["observed_agreement"] == 1.0
    assert report["cohen_kappa"] == 1.0
    assert report["confusion_matrix"]["Applicable"]["Applicable"] == 1


def test_agreement_report_computes_disagreement():
    report = agreement_report([
        item("Applicable", "Not applicable", "1"),
        item("Not applicable", "Applicable", "2"),
        item("Conflict", "Conflict", "3"),
        item("Indeterminate", "Indeterminate", "4"),
    ])
    assert report["n_paired"] == 4
    assert report["observed_agreement"] == 0.5
    assert report["cohen_kappa"] < 1.0


def test_unpaired_annotations_are_excluded_not_counted_as_disagreement():
    report = agreement_report([
        item("Applicable", None, "1"),
        item(None, None, "2"),
        item("Indeterminate", "Indeterminate", "3"),
    ])
    assert report["n_paired"] == 1
    assert report["n_excluded"] == 2
    assert report["cohen_kappa"] == 1.0


def test_no_paired_annotations_returns_null_not_zero():
    report = agreement_report([item(None, None)])
    assert report["n_paired"] == 0
    assert report["cohen_kappa"] is None
    assert "not computable" in report["interpretation"]


def test_load_items_rejects_bad_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"annotations": {}}\n{bad json}\n', encoding="utf-8")
    try:
        load_items(path)
    except ValueError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("Expected malformed JSONL to be rejected")


def test_load_items_ignores_blank_and_comment_lines(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text(
        '# annotation file\n\n' + json.dumps(item("Applicable", "Applicable")) + '\n',
        encoding="utf-8",
    )
    assert len(load_items(path)) == 1
