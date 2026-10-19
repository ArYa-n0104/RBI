from __future__ import annotations

from taarr.experiments import run_experiments
from taarr.models import (
    MissingFactsPolicy,
    NoVersionPolicy,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)


def policy() -> ResolverPolicy:
    return ResolverPolicy(
        no_version=NoVersionPolicy.NOT_APPLICABLE,
        missing_facts=MissingFactsPolicy.KLEENE,
        unknown_precedence=UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST,
    )


def test_runner_reports_unavailable_metrics_for_empty_gold(tmp_path):
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        '{"benchmark_item_id":"draft","annotation_status":"draft","gold_outcome":"Applicable"}\n',
        encoding="utf-8",
    )
    result = run_experiments(
        str(benchmark),
        "data/obligations/obligations.jsonl",
        policy(),
    )
    assert result["gold_n"] == 0
    assert result["drafts_excluded_n"] == 1
    assert set(result["experiments"]) == {
        "full_taarr",
        "ablation_no_temporal",
        "ablation_no_abstention",
        "ablation_no_exemptions_dependencies",
    }
    assert all(
        experiment["metrics"]["status"] == "unavailable"
        and experiment["metrics"]["accuracy"] is None
        for experiment in result["experiments"].values()
    )


def test_runner_scores_only_gold_verified_items(tmp_path):
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        '{"benchmark_item_id":"gold-1","annotation_status":"gold_verified",'
        '"gold_outcome":"Applicable","target_obligation_id":"RBI-KYC-P38E-DUE-NOTICES",'
        '"reference_date":"2025-07-01","entity_profile":{"is_rbi_regulated_entity":true}}\n'
        '{"benchmark_item_id":"draft-1","annotation_status":"draft",'
        '"gold_outcome":"Not applicable","target_obligation_id":"RBI-KYC-P38E-DUE-NOTICES",'
        '"reference_date":"2025-07-01","entity_profile":{"is_rbi_regulated_entity":false}}\n',
        encoding="utf-8",
    )
    result = run_experiments(
        str(benchmark),
        "data/obligations/obligations.jsonl",
        policy(),
    )
    assert result["gold_n"] == 1
    assert result["drafts_excluded_n"] == 1
    full = result["experiments"]["full_taarr"]["metrics"]
    assert full["gold_n"] == 1
    assert full["matched_n"] == 1
    assert full["accuracy"] in {0.0, 1.0}
