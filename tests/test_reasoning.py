from __future__ import annotations

from datetime import date

import pytest

from taarr.models import (
    ClauseVersion,
    DependencyRule,
    ExceptionEffect,
    ExceptionRule,
    MissingFactsPolicy,
    NoVersionPolicy,
    Obligation,
    Outcome,
    ResolverPolicy,
    TruthValue,
    UnknownPrecedencePolicy,
)
from taarr.reasoning import evaluate_condition, resolve_obligation


REFERENCE_DATE = date(2025, 7, 1)
SOURCE_URL = "https://www.rbi.org.in/example"


def policy(
    no_version=NoVersionPolicy.DROP,
    missing_facts=MissingFactsPolicy.KLEENE,
    unknown_precedence=UnknownPrecedencePolicy.INDETERMINATE_FIRST,
):
    return ResolverPolicy(
        no_version=no_version,
        missing_facts=missing_facts,
        unknown_precedence=unknown_precedence,
    )


def version(
    obligation_id="OBL-1",
    version_id="OBL-1-v1",
    effective_from=date(2025, 1, 1),
    effective_to=None,
    condition=None,
    clause_text="Example obligation",
    exemptions=(),
    dependencies=(),
    precedence=None,
):
    return ClauseVersion(
        obligation_id=obligation_id,
        version_id=version_id,
        clause_id=f"clause-{version_id}",
        official_url=SOURCE_URL,
        clause_text=clause_text,
        effective_from=effective_from,
        effective_to=effective_to,
        applicability_condition=condition or {
            "attribute": "is_rbi_regulated_entity",
            "operator": "equals",
            "value": True,
        },
        exemptions=tuple(exemptions),
        dependencies=tuple(dependencies),
        precedence=precedence,
    )


def obligation(*versions, obligation_id="OBL-1"):
    return Obligation(obligation_id=obligation_id, versions=tuple(versions))


def resolve(record, profile, resolver_policy=None, records=None, on_date=REFERENCE_DATE):
    kb = records or {record.obligation_id: record}
    return resolve_obligation(
        record.obligation_id, kb, on_date, profile, resolver_policy or policy()
    )


def test_three_valued_condition_evaluation_for_missing_fact():
    result = evaluate_condition(
        {"attribute": "entity.layer", "operator": "equals", "value": "upper"},
        {"entity": {"type": "NBFC"}},
    )
    assert result.value == TruthValue.UNKNOWN
    assert result.missing_facts == ("entity.layer",)


def test_kleene_and_false_dominates_unknown():
    result = evaluate_condition(
        {
            "all_of": [
                {"attribute": "is_rbi_regulated_entity", "operator": "equals", "value": True},
                {"attribute": "entity.layer", "operator": "equals", "value": "upper"},
            ]
        },
        {"is_rbi_regulated_entity": False},
    )
    assert result.value == TruthValue.FALSE
    assert result.missing_facts == ("entity.layer",)


def test_kleene_or_true_dominates_unknown():
    result = evaluate_condition(
        {
            "any_of": [
                {"attribute": "is_rbi_regulated_entity", "operator": "equals", "value": True},
                {"attribute": "entity.layer", "operator": "equals", "value": "upper"},
            ]
        },
        {"is_rbi_regulated_entity": True},
    )
    assert result.value == TruthValue.TRUE


def test_not_unknown_stays_unknown():
    result = evaluate_condition(
        {"not": {"attribute": "fact", "operator": "equals", "value": True}}, {}
    )
    assert result.value == TruthValue.UNKNOWN


def test_unsupported_condition_operator_is_rejected():
    with pytest.raises(ValueError, match="Unsupported condition operator"):
        evaluate_condition({"attribute": "x", "operator": "maybe", "value": 1}, {"x": 1})


def test_effective_from_is_inclusive():
    record = obligation(version(effective_from=REFERENCE_DATE))
    result = resolve(record, {"is_rbi_regulated_entity": True})
    assert result is not None
    assert result.outcome == Outcome.APPLICABLE


def test_effective_to_is_exclusive():
    record = obligation(version(effective_from=date(2025, 1, 1), effective_to=REFERENCE_DATE))
    result = resolve(record, {"is_rbi_regulated_entity": True})
    assert result is None


def test_no_version_policy_drop_returns_none():
    record = obligation(version(effective_from=date(2025, 7, 2)))
    assert resolve(
        record,
        {"is_rbi_regulated_entity": True},
        policy(no_version=NoVersionPolicy.DROP),
    ) is None


def test_no_version_policy_not_applicable_emits_evidence():
    record = obligation(version(effective_from=date(2025, 7, 2)))
    result = resolve(
        record,
        {"is_rbi_regulated_entity": True},
        policy(no_version=NoVersionPolicy.NOT_APPLICABLE),
    )
    assert result is not None
    assert result.outcome == Outcome.NOT_APPLICABLE
    assert result.evidence[0]["kind"] == "temporal_filter"


def test_overlapping_different_text_without_precedence_is_conflict():
    record = obligation(
        version(version_id="v1", clause_text="old text"),
        version(version_id="v2", clause_text="new text"),
    )
    result = resolve(record, {"is_rbi_regulated_entity": True})
    assert result is not None
    assert result.outcome == Outcome.CONFLICT
    assert len(result.evidence) == 2


def test_overlapping_different_text_with_unique_source_precedence_selects_winner():
    record = obligation(
        version(version_id="v1", clause_text="old text", precedence=1),
        version(version_id="v2", clause_text="new text", precedence=2),
    )
    result = resolve(record, {"is_rbi_regulated_entity": True})
    assert result is not None
    assert result.outcome == Outcome.APPLICABLE
    assert result.version_id == "v2"


def test_missing_fact_returns_indeterminate():
    record = obligation(version())
    result = resolve(record, {})
    assert result is not None
    assert result.outcome == Outcome.INDETERMINATE
    assert result.missing_facts == ("is_rbi_regulated_entity",)


def test_strict_missing_policy_returns_indeterminate_even_if_another_condition_is_false():
    record = obligation(version(condition={
        "all_of": [
            {"attribute": "is_rbi_regulated_entity", "operator": "equals", "value": True},
            {"attribute": "entity.layer", "operator": "equals", "value": "upper"},
        ]
    }))
    result = resolve(
        record,
        {"is_rbi_regulated_entity": False},
        policy(missing_facts=MissingFactsPolicy.STRICT_MISSING),
    )
    assert result is not None
    assert result.outcome == Outcome.INDETERMINATE


def test_false_applicability_is_not_applicable():
    record = obligation(version())
    result = resolve(record, {"is_rbi_regulated_entity": False})
    assert result is not None
    assert result.outcome == Outcome.NOT_APPLICABLE


def test_active_exemption_makes_obligation_not_applicable():
    exception = ExceptionRule(
        relation_id="EX-1",
        clause_id="exemption-1",
        official_url=SOURCE_URL,
        condition={"attribute": "entity.exempt", "operator": "equals", "value": True},
        effect=ExceptionEffect.EXEMPT,
        effective_from=date(2025, 1, 1),
    )
    record = obligation(version(exemptions=(exception,)))
    result = resolve(record, {"is_rbi_regulated_entity": True, "entity": {"exempt": True}})
    assert result is not None
    assert result.outcome == Outcome.NOT_APPLICABLE
    assert any(item.get("kind") == "exemption_rule" for item in result.evidence)


def test_equal_priority_opposing_exemption_effects_are_conflict():
    rules = (
        ExceptionRule(
            relation_id="EX-1", clause_id="exemption-1", official_url=SOURCE_URL,
            condition={"attribute": "entity.exempt", "operator": "equals", "value": True},
            effect=ExceptionEffect.EXEMPT, effective_from=date(2025, 1, 1), priority=5,
        ),
        ExceptionRule(
            relation_id="EX-2", clause_id="exemption-2", official_url=SOURCE_URL,
            condition={"attribute": "entity.exempt", "operator": "equals", "value": True},
            effect=ExceptionEffect.NOT_EXEMPT, effective_from=date(2025, 1, 1), priority=5,
        ),
    )
    record = obligation(version(exemptions=rules))
    result = resolve(record, {"is_rbi_regulated_entity": True, "entity": {"exempt": True}})
    assert result is not None
    assert result.outcome == Outcome.CONFLICT


def test_missing_applicability_fact_can_be_resolved_by_known_exemption_under_definitive_first():
    exception = ExceptionRule(
        relation_id="EX-1",
        clause_id="exemption-1",
        official_url=SOURCE_URL,
        condition={"attribute": "entity.exempt", "operator": "equals", "value": True},
        effect=ExceptionEffect.EXEMPT,
        effective_from=date(2025, 1, 1),
    )
    record = obligation(version(exemptions=(exception,)))
    result = resolve(
        record,
        {"entity": {"exempt": True}},
        policy(unknown_precedence=UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST),
    )
    assert result is not None
    assert result.outcome == Outcome.NOT_APPLICABLE


def test_missing_applicability_fact_wins_under_indeterminate_first_policy():
    exception = ExceptionRule(
        relation_id="EX-1",
        clause_id="exemption-1",
        official_url=SOURCE_URL,
        condition={"attribute": "entity.exempt", "operator": "equals", "value": True},
        effect=ExceptionEffect.EXEMPT,
        effective_from=date(2025, 1, 1),
    )
    record = obligation(version(exemptions=(exception,)))
    result = resolve(
        record,
        {"entity": {"exempt": True}},
        policy(unknown_precedence=UnknownPrecedencePolicy.INDETERMINATE_FIRST),
    )
    assert result is not None
    assert result.outcome == Outcome.INDETERMINATE


def test_not_applicable_dependency_makes_dependent_not_applicable():
    dependency = DependencyRule(
        relation_id="DEP-1",
        target_obligation_id="OBL-PREREQ",
        clause_id="dependency-clause",
        official_url=SOURCE_URL,
    )
    target = obligation(version(dependencies=(dependency,)), obligation_id="OBL-1")
    prerequisite = obligation(
        version(
            obligation_id="OBL-PREREQ",
            version_id="OBL-PREREQ-v1",
            condition={"attribute": "required", "operator": "equals", "value": True},
        ),
        obligation_id="OBL-PREREQ",
    )
    result = resolve(
        target,
        {"is_rbi_regulated_entity": True, "required": False},
        records={"OBL-1": target, "OBL-PREREQ": prerequisite},
    )
    assert result is not None
    assert result.outcome == Outcome.NOT_APPLICABLE
    assert result.dependency_results[0].outcome == Outcome.NOT_APPLICABLE


def test_dependency_cycle_is_conflict():
    to_b = DependencyRule("DEP-A-B", "B", "clause-a-b", SOURCE_URL)
    to_a = DependencyRule("DEP-B-A", "A", "clause-b-a", SOURCE_URL)
    a = obligation(version(obligation_id="A", version_id="A-v1", dependencies=(to_b,)), obligation_id="A")
    b = obligation(version(obligation_id="B", version_id="B-v1", dependencies=(to_a,)), obligation_id="B")
    result = resolve(a, {"is_rbi_regulated_entity": True}, records={"A": a, "B": b})
    assert result is not None
    assert result.outcome == Outcome.CONFLICT


def test_result_to_dict_contains_explicit_outcome_and_provenance():
    record = obligation(version())
    result = resolve(record, {"is_rbi_regulated_entity": True})
    assert result is not None
    payload = result.to_dict()
    assert payload["outcome"] == "Applicable"
    assert payload["evidence"][0]["source_url"] == SOURCE_URL
    assert payload["reference_date"] == "2025-07-01"
