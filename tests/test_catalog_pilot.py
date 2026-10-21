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


SEBI_TARGET = "SEBI-LODR-REG15-2B-SME-RPT-APPLICABILITY"


PARA17_TARGET = "RBI-KYC-PARA17-OTP-EKYC-BALANCE-CAP"


def test_pilot_catalog_loads_both_obligations_with_their_exemptions():
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.obligation_count == 9
    version = catalog.obligations[TARGET].versions[0]
    assert len(version.exemptions) == 1
    assert version.exemptions[0].relation_id == "RBI-KYC-PARA2-SMALL-ACCOUNT-PROVISO"

    pan_version = catalog.obligations["RBI-KYC-PARA39-PAN-FORM60"].versions[0]
    assert len(pan_version.exemptions) == 1
    assert pan_version.exemptions[0].relation_id == "RBI-KYC-PARA39-INFIRMITY-RELAXATION"

    sebi_version = catalog.obligations[SEBI_TARGET].versions[0]
    assert len(sebi_version.exemptions) == 0
    sebi_raw = catalog.records_for_obligation(SEBI_TARGET)
    assert sebi_raw[0]["regulator"] == "SEBI"

    para17_raw = catalog.records_for_obligation(PARA17_TARGET)
    assert para17_raw[0]["regulator"] == "RBI"
    assert para17_raw[0]["verification_status"] == "source_text_human_confirmed"


def test_para17_balance_cap_applies_for_otp_ekyc_account():
    outcome = _resolve_for(PARA17_TARGET, date(2025, 9, 1), {"is_otp_based_ekyc_account": True})
    assert outcome == Outcome.APPLICABLE


def test_para17_balance_cap_not_applicable_for_full_kyc_account():
    outcome = _resolve_for(PARA17_TARGET, date(2025, 9, 1), {"is_otp_based_ekyc_account": False})
    assert outcome == Outcome.NOT_APPLICABLE


def test_para17_balance_cap_indeterminate_when_account_type_unknown():
    outcome = _resolve_for(PARA17_TARGET, date(2025, 9, 1), {})
    assert outcome == Outcome.INDETERMINATE


WALKIN_TARGET = "RBI-KYC-PARA13-WALKIN-THRESHOLD"
PEP_TARGET = "RBI-KYC-PARA41A-PEP-APPROVAL"
VCIP_TARGET = "RBI-KYC-PARA18C-VCIP-DATA-LOCALIZATION"
NONF2F_TARGET = "RBI-KYC-PARA40F-NONFACETOFACE-HIGHRISK"
RETENTION_TARGET = "RBI-KYC-PARA46A-RECORD-RETENTION"


def test_catalog_grew_to_nine_obligations():
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.obligation_count == 9


def test_walkin_threshold_applies_at_or_above_fifty_thousand():
    outcome = _resolve_for(
        WALKIN_TARGET, date(2025, 9, 1),
        {"is_walk_in_customer": True, "transaction_amount_rupees": 75000},
    )
    assert outcome == Outcome.APPLICABLE


def test_walkin_threshold_not_applicable_below_fifty_thousand():
    outcome = _resolve_for(
        WALKIN_TARGET, date(2025, 9, 1),
        {"is_walk_in_customer": True, "transaction_amount_rupees": 20000},
    )
    assert outcome == Outcome.NOT_APPLICABLE


def test_walkin_threshold_indeterminate_when_amount_unknown():
    outcome = _resolve_for(WALKIN_TARGET, date(2025, 9, 1), {"is_walk_in_customer": True})
    assert outcome == Outcome.INDETERMINATE


def test_pep_approval_applies_for_pep_customer():
    outcome = _resolve_for(PEP_TARGET, date(2025, 9, 1), {"is_politically_exposed_person": True})
    assert outcome == Outcome.APPLICABLE


def test_pep_approval_not_applicable_for_ordinary_customer():
    outcome = _resolve_for(PEP_TARGET, date(2025, 9, 1), {"is_politically_exposed_person": False})
    assert outcome == Outcome.NOT_APPLICABLE


def test_vcip_data_localization_applies_when_vcip_used():
    outcome = _resolve_for(VCIP_TARGET, date(2025, 9, 1), {"uses_vcip_onboarding": True})
    assert outcome == Outcome.APPLICABLE


def test_vcip_data_localization_not_applicable_without_vcip():
    outcome = _resolve_for(VCIP_TARGET, date(2025, 9, 1), {"uses_vcip_onboarding": False})
    assert outcome == Outcome.NOT_APPLICABLE


def test_nonf2f_highrisk_applies_for_non_face_to_face_onboarding():
    outcome = _resolve_for(NONF2F_TARGET, date(2025, 9, 1), {"is_non_face_to_face_onboarding": True})
    assert outcome == Outcome.APPLICABLE


def test_nonf2f_highrisk_not_applicable_for_in_person_onboarding():
    outcome = _resolve_for(NONF2F_TARGET, date(2025, 9, 1), {"is_non_face_to_face_onboarding": False})
    assert outcome == Outcome.NOT_APPLICABLE


def test_record_retention_applies_to_rbi_regulated_entity():
    outcome = _resolve_for(RETENTION_TARGET, date(2025, 9, 1), {"is_rbi_regulated_entity": True})
    assert outcome == Outcome.APPLICABLE


def test_record_retention_not_applicable_outside_scope():
    outcome = _resolve_for(RETENTION_TARGET, date(2025, 9, 1), {"is_rbi_regulated_entity": False})
    assert outcome == Outcome.NOT_APPLICABLE


def test_sebi_sme_rpt_applies_above_equity_capital_threshold():
    outcome = _resolve_for(
        SEBI_TARGET,
        date(2025, 6, 1),
        {"is_sme_exchange_listed": True, "paid_up_equity_capital_crore": 12, "net_worth_crore": 5},
    )
    assert outcome == Outcome.APPLICABLE


def test_sebi_sme_rpt_applies_above_net_worth_threshold_alone():
    outcome = _resolve_for(
        SEBI_TARGET,
        date(2025, 6, 1),
        {"is_sme_exchange_listed": True, "paid_up_equity_capital_crore": 2, "net_worth_crore": 30},
    )
    assert outcome == Outcome.APPLICABLE


def test_sebi_sme_rpt_not_applicable_below_both_thresholds():
    outcome = _resolve_for(
        SEBI_TARGET,
        date(2025, 6, 1),
        {"is_sme_exchange_listed": True, "paid_up_equity_capital_crore": 6, "net_worth_crore": 8},
    )
    assert outcome == Outcome.NOT_APPLICABLE


def test_sebi_sme_rpt_indeterminate_when_one_threshold_fact_is_missing():
    """If equity capital is below threshold but net worth is unknown, the unknown fact
    could independently trigger applicability -- the resolver must abstain, not assume."""
    outcome = _resolve_for(
        SEBI_TARGET,
        date(2025, 6, 1),
        {"is_sme_exchange_listed": True, "paid_up_equity_capital_crore": 4},
    )
    assert outcome == Outcome.INDETERMINATE


def test_sebi_sme_rpt_not_applicable_before_effective_date():
    outcome = _resolve_for(
        SEBI_TARGET,
        date(2025, 1, 1),
        {"is_sme_exchange_listed": True, "paid_up_equity_capital_crore": 50, "net_worth_crore": 50},
    )
    assert outcome == Outcome.NOT_APPLICABLE


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
