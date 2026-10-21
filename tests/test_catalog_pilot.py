"""Regression tests against the real pilot catalog in data/obligations/obligations.jsonl.

Unlike test_reasoning.py (synthetic fixtures), this exercises the deterministic
resolver against the actual source-grounded pilot record, including the
paragraph-2 small-account exemption on RBI-KYC-P38E-DUE-NOTICES. These are
draft/source-located records, not gold-verified; this test only pins
*engine behavior* on real catalog data, not a legal conclusion.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from taarr.catalog import load_catalog
from taarr.models import (
    MissingFactsPolicy,
    NoVersionPolicy,
    Outcome,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)
from taarr.reasoning import resolve_obligation

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "obligations" / "obligations.jsonl"
POLICY = ResolverPolicy(
    no_version=NoVersionPolicy.NOT_APPLICABLE,
    missing_facts=MissingFactsPolicy.KLEENE,
    unknown_precedence=UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST,
)
TARGET = "RBI-KYC-P38E-DUE-NOTICES"


def _resolve(reference_date: date, profile: dict) -> Outcome:
    return _resolve_for(TARGET, reference_date, profile)


def _resolve_for(obligation_id: str, reference_date: date, profile: dict) -> Outcome:
    catalog = load_catalog(CATALOG_PATH)
    result = resolve_obligation(obligation_id, catalog.obligations, reference_date, profile, POLICY)
    assert result is not None
    return result.outcome


def test_pilot_catalog_loads_both_obligations_with_their_exemptions():
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.obligation_count == 2
    version = catalog.obligations[TARGET].versions[0]
    assert len(version.exemptions) == 1
    assert version.exemptions[0].relation_id == "RBI-KYC-PARA2-SMALL-ACCOUNT-PROVISO"

    pan_version = catalog.obligations["RBI-KYC-PARA39-PAN-FORM60"].versions[0]
    assert len(pan_version.exemptions) == 1
    assert pan_version.exemptions[0].relation_id == "RBI-KYC-PARA39-INFIRMITY-RELAXATION"


def test_pan_form60_applies_when_no_infirmity_relaxation_is_known_false():
    outcome = _resolve_for(
        "RBI-KYC-PARA39-PAN-FORM60",
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True, "customer_unable_due_to_infirmity": False},
    )
    assert outcome == Outcome.APPLICABLE


def test_pan_form60_infirmity_relaxation_applies():
    outcome = _resolve_for(
        "RBI-KYC-PARA39-PAN-FORM60",
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True, "customer_unable_due_to_infirmity": True},
    )
    assert outcome == Outcome.NOT_APPLICABLE


def test_pan_form60_unknown_infirmity_status_is_indeterminate():
    """Omitting the exemption fact (rather than setting it explicitly False) must not be
    silently treated as 'exemption doesn't apply' -- it must abstain."""
    outcome = _resolve_for(
        "RBI-KYC-PARA39-PAN-FORM60",
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True},
    )
    assert outcome == Outcome.INDETERMINATE


def test_small_account_exemption_applies_after_its_effective_date():
    outcome = _resolve(
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True, "is_small_account": True},
    )
    assert outcome == Outcome.NOT_APPLICABLE


def test_small_account_exemption_not_yet_active_before_its_effective_date():
    """The exemption's effective_from (2025-08-14) postdates the target obligation's
    (2025-06-12); before that date the obligation applies normally."""
    outcome = _resolve(
        date(2025, 7, 1),
        {"is_rbi_regulated_entity": True, "is_small_account": True},
    )
    assert outcome == Outcome.APPLICABLE


def test_unknown_small_account_status_is_indeterminate_under_d003():
    """D-003 (DEFINITIVE_RULES_FIRST): applicability is known true, but the exemption's
    own condition is unknown, so a known-false sibling cannot settle it either -> abstain."""
    outcome = _resolve(
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True},
    )
    assert outcome == Outcome.INDETERMINATE


def test_non_small_account_remains_applicable():
    outcome = _resolve(
        date(2025, 9, 1),
        {"is_rbi_regulated_entity": True, "is_small_account": False},
    )
    assert outcome == Outcome.APPLICABLE
