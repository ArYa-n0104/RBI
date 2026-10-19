from __future__ import annotations

import json

from taarr.dataset import validate_file, validate_item


def valid_item():
    return {
        "benchmark_item_id": "TAARR-BENCH-TEST-0001",
        "query": "Synthetic test fixture; not a real legal conclusion.",
        "reference_date": "2025-01-01",
        "entity_profile": {"entity_type": "synthetic_test_entity"},
        "missing_facts_intentionally_omitted": [],
        "target_obligation_id": "TEST-OBL-1",
        "gold_obligations": [
            {
                "obligation_id": "TEST-OBL-1",
                "version_id": "TEST-OBL-1-v1",
                "instrument_id": "TEST-INSTRUMENT",
                "clause_id": "clause-1",
                "official_url": "https://example.org/test-source",
                "clause_text": "Synthetic fixture text, not regulatory material.",
                "role": "target",
            }
        ],
        "effective_dates": [
            {
                "version_id": "TEST-OBL-1-v1",
                "publication_date": "2024-01-01",
                "effective_from": "2024-01-01",
                "effective_to": None,
                "amendment_lineage": [],
            }
        ],
        "exemptions_dependencies": [],
        "gold_outcome": "Indeterminate",
        "gold_explanation": "Synthetic fixture only.",
        "annotation_status": "draft",
        "annotations": {},
        "scenario_tags": ["synthetic_test_only"],
        "split_group_id": "synthetic-fixture-group",
    }


def test_valid_item_has_no_structural_errors():
    assert validate_item(valid_item()) == []


def test_invalid_outcome_is_rejected():
    item = valid_item()
    item["gold_outcome"] = "Maybe"
    assert any("gold_outcome" in error for error in validate_item(item))


def test_target_obligation_must_exist_in_gold_obligations():
    item = valid_item()
    item["target_obligation_id"] = "MISSING"
    assert any("target_obligation_id" in error for error in validate_item(item))


def test_target_obligation_must_have_target_role():
    item = valid_item()
    item["gold_obligations"][0]["role"] = "supporting"
    assert any("role='target'" in error for error in validate_item(item))


def test_target_version_must_have_date_evidence():
    item = valid_item()
    item["effective_dates"] = []
    assert any("effective_dates must contain" in error for error in validate_item(item))


def test_non_canonical_date_format_is_rejected():
    item = valid_item()
    item["reference_date"] = "20250101"
    assert any("reference_date" in error for error in validate_item(item))


def test_date_interval_must_be_ordered():
    item = valid_item()
    item["effective_dates"][0]["effective_to"] = "2023-01-01"
    assert any("effective_from must be earlier" in error for error in validate_item(item))


def test_dual_annotated_requires_both_independent_labels():
    item = valid_item()
    item["annotation_status"] = "dual_annotated"
    assert any("annotator_1.outcome" in error for error in validate_item(item))
    assert any("annotator_2.outcome" in error for error in validate_item(item))


def test_gold_verified_requires_two_annotators_and_adjudication():
    item = valid_item()
    item["annotation_status"] = "gold_verified"
    item["annotations"] = {
        "annotator_1": {"outcome": "Applicable"},
        "annotator_2": {"outcome": "Indeterminate"},
        "adjudication": {"outcome": "Indeterminate"},
    }
    assert validate_item(item) == []
    item["gold_outcome"] = "Applicable"
    assert any("must match adjudication.outcome" in error for error in validate_item(item))


def test_empty_comment_only_ledger_is_valid_and_has_zero_items(tmp_path):
    path = tmp_path / "benchmark.jsonl"
    path.write_text("# no gold items yet\n\n", encoding="utf-8")
    count, errors = validate_file(path)
    assert count == 0
    assert errors == []


def test_file_validator_detects_duplicates_and_bad_json(tmp_path):
    item = valid_item()
    path = tmp_path / "benchmark.jsonl"
    path.write_text(
        json.dumps(item) + "\n" + json.dumps(item) + "\n{invalid json}\n",
        encoding="utf-8",
    )
    count, errors = validate_file(path)
    assert count == 2
    assert any("duplicate benchmark_item_id" in error for error in errors)
    assert any("invalid JSON" in error for error in errors)
