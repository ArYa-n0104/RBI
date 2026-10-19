from __future__ import annotations

from taarr.provenance_audit import audit_records


def catalog_record(**overrides):
    record = {
        "obligation_id": "O1",
        "version_id": "V1",
        "clause_id": "P1",
        "source_url": "https://www.rbi.org.in/example",
        "effective_from": "2025-01-01",
        "effective_to": None,
        "verification_status": "source_located_clause_not_gold_verified",
        "exemptions": [],
        "dependencies": [],
    }
    record.update(overrides)
    return record


def gold_item(**overrides):
    item = {
        "benchmark_item_id": "B1",
        "annotation_status": "gold_verified",
        "gold_outcome": "Applicable",
        "split_group_id": "O1-lineage",
        "split": "test",
        "annotations": {"adjudication": {"outcome": "Applicable", "reviewer": "reviewer-1"}},
        "gold_obligations": [
            {
                "obligation_id": "O1",
                "version_id": "V1",
                "clause_id": "P1",
                "official_url": "https://www.rbi.org.in/example",
            }
        ],
    }
    item.update(overrides)
    return item


def test_empty_gold_is_review_not_successful_evaluation():
    result = audit_records([catalog_record()], [])
    assert result["status"] == "needs_review"
    assert result["gold_verified_n"] == 0
    assert result["error_count"] == 0


def test_valid_gold_reference_and_adjudication_pass_structural_checks():
    result = audit_records([catalog_record(verification_status="gold_verified")], [gold_item()])
    assert result["status"] == "checks_passed"
    assert result["gold_verified_n"] == 1
    assert result["gold_outcome_counts"]["Applicable"] == 1


def test_non_official_source_is_blocking():
    result = audit_records([catalog_record(source_url="https://example.com/clause")], [])
    assert result["status"] == "blocked"
    assert any(issue["code"] == "NON_OFFICIAL_SOURCE" for issue in result["issues"])


def test_gold_clause_mismatch_and_missing_adjudication_are_blocking():
    item = gold_item(annotations={})
    result = audit_records([catalog_record(verification_status="gold_verified")], [item])
    codes = {issue["code"] for issue in result["issues"]}
    assert "GOLD_ADJUDICATION_MISSING" in codes


def test_related_items_in_different_splits_are_blocking():
    first = {"benchmark_item_id": "B1", "annotation_status": "draft", "split_group_id": "lineage", "split": "train"}
    second = {"benchmark_item_id": "B2", "annotation_status": "draft", "split_group_id": "lineage", "split": "test"}
    result = audit_records([], [first, second])
    assert result["status"] == "blocked"
    assert result["split_group_leakage"] == ["lineage"]


def test_duplicate_version_and_item_ids_are_blocking():
    result = audit_records([catalog_record(), catalog_record()], [
        {"benchmark_item_id": "B1", "annotation_status": "draft"},
        {"benchmark_item_id": "B1", "annotation_status": "draft"},
    ])
    codes = {issue["code"] for issue in result["issues"]}
    assert "DUPLICATE_VERSION" in codes
    assert "DUPLICATE_ITEM_ID" in codes
