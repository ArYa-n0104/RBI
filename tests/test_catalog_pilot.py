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
    catalog = load_catalog(CATALOG_PATH)
    result = resolve_obligation(TARGET, catalog.obligations, reference_date, profile, POLICY)
    assert result is not None
    return result.outcome


def test_pilot_catalog_loads_one_obligation_with_one_exemption():
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.obligation_count == 1
    version = catalog.obligations[TARGET].versions[0]
    assert len(version.exemptions) == 1
    assert version.exemptions[0].relation_id == "RBI-KYC-PARA2-SMALL-ACCOUNT-PROVISO"


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
