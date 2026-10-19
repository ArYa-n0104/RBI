"""Deterministic, auditable TAARR obligation resolution.

No LLM or probabilistic model is used in this module. Conditions use Kleene
three-valued logic; date intervals are start-inclusive and end-exclusive.
Policy choices that differ between the supplied project documents are explicit
configuration values in ResolverPolicy, never hidden fallbacks.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .models import (
    ClauseVersion,
    Condition,
    ConditionEvaluation,
    DependencyRule,
    ExceptionEffect,
    ExceptionRule,
    MissingFactsPolicy,
    NoVersionPolicy,
    Obligation,
    Outcome,
    ResolutionResult,
    ResolverPolicy,
    TruthValue,
    UnknownPrecedencePolicy,
)


def _get_attribute(profile: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Read an attribute using dot-separated paths, returning present/value."""
    current: Any = profile
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    if current is None:
        return False, None
    return True, current


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate one supported, deterministic comparison operator."""
    if operator in {"equals", "eq"}:
        return actual == expected
    if operator in {"not_equals", "ne"}:
        return actual != expected
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "in":
        if not isinstance(expected, (list, tuple, set, frozenset, str)):
            raise ValueError("'in' operator requires a collection or string value")
        return actual in expected
    if operator == "not_in":
        if not isinstance(expected, (list, tuple, set, frozenset, str)):
            raise ValueError("'not_in' operator requires a collection or string value")
        return actual not in expected
    if operator == "contains":
        if not isinstance(actual, (list, tuple, set, frozenset, str, dict)):
            return False
        return expected in actual
    raise ValueError(f"Unsupported condition operator: {operator!r}")


def evaluate_condition(condition: Condition, profile: dict[str, Any]) -> ConditionEvaluation:
    """Evaluate JSON-shaped logical predicates with Kleene three-valued logic.

    Supported nodes: all_of, any_of, not, and atomic {attribute, operator, value}.
    A missing/null attribute yields UNKNOWN. Empty all_of is TRUE; empty any_of
    is FALSE. Malformed or unsupported predicates raise ValueError.
    """
    if not isinstance(condition, dict):
        raise ValueError("A condition must be a JSON object")

    if "all_of" in condition:
        children = condition["all_of"]
        if not isinstance(children, list):
            raise ValueError("'all_of' must be a list")
        evaluations = [evaluate_condition(child, profile) for child in children]
        if any(child.value == TruthValue.FALSE for child in evaluations):
            value = TruthValue.FALSE
        elif any(child.value == TruthValue.UNKNOWN for child in evaluations):
            value = TruthValue.UNKNOWN
        else:
            value = TruthValue.TRUE
        return _combine_evaluations("all_of", value, evaluations)

    if "any_of" in condition:
        children = condition["any_of"]
        if not isinstance(children, list):
            raise ValueError("'any_of' must be a list")
        evaluations = [evaluate_condition(child, profile) for child in children]
        if any(child.value == TruthValue.TRUE for child in evaluations):
            value = TruthValue.TRUE
        elif any(child.value == TruthValue.UNKNOWN for child in evaluations):
            value = TruthValue.UNKNOWN
        else:
            value = TruthValue.FALSE
        return _combine_evaluations("any_of", value, evaluations)

    if "not" in condition:
        child = evaluate_condition(condition["not"], profile)
        if child.value == TruthValue.TRUE:
            value = TruthValue.FALSE
        elif child.value == TruthValue.FALSE:
            value = TruthValue.TRUE
        else:
            value = TruthValue.UNKNOWN
        trace = ({"kind": "condition", "operator": "not", "value": value.value},) + child.trace
        return ConditionEvaluation(value, child.missing_facts, trace)

    attribute = condition.get("attribute")
    operator = condition.get("operator")
    if not isinstance(attribute, str) or not attribute.strip():
        raise ValueError("An atomic condition requires a non-empty 'attribute'")
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError(f"Condition {attribute!r} requires an 'operator'")

    present, actual = _get_attribute(profile, attribute)
    if not present:
        trace = ({
            "kind": "predicate",
            "attribute": attribute,
            "operator": operator,
            "expected": condition.get("value"),
            "value": TruthValue.UNKNOWN.value,
        },)
        return ConditionEvaluation(TruthValue.UNKNOWN, (attribute,), trace)

    try:
        matched = _compare(actual, operator, condition.get("value"))
    except TypeError:
        # Wrongly typed facts cannot safely be coerced. Treat them as unknown and
        # expose the field for correction rather than guessing a legal conclusion.
        trace = ({
            "kind": "predicate",
            "attribute": attribute,
            "operator": operator,
            "actual_type": type(actual).__name__,
            "expected": condition.get("value"),
            "value": TruthValue.UNKNOWN.value,
            "note": "incompatible fact type",
        },)
        return ConditionEvaluation(TruthValue.UNKNOWN, (attribute,), trace)

    value = TruthValue.TRUE if matched else TruthValue.FALSE
    trace = ({
        "kind": "predicate",
        "attribute": attribute,
        "operator": operator,
        "actual": actual,
        "expected": condition.get("value"),
        "value": value.value,
    },)
    return ConditionEvaluation(value, (), trace)


def _combine_evaluations(
    operator: str,
    value: TruthValue,
    children: Iterable[ConditionEvaluation],
) -> ConditionEvaluation:
    evaluations = tuple(children)
    missing = tuple(sorted({fact for item in evaluations for fact in item.missing_facts}))
    trace = ({"kind": "condition", "operator": operator, "value": value.value},)
    trace += tuple(node for item in evaluations for node in item.trace)
    return ConditionEvaluation(value, missing, trace)


def _evidence_for_version(version: ClauseVersion, selected: bool) -> dict[str, Any]:
    return {
        "kind": "clause_version",
        "obligation_id": version.obligation_id,
        "version_id": version.version_id,
        "clause_id": version.clause_id,
        "source_url": version.official_url,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "selected": selected,
    }


def _resolve_version(
    obligation: Obligation,
    reference_date: date,
) -> tuple[ClauseVersion | None, ResolutionResult | None]:
    active = tuple(version for version in obligation.versions if version.is_active(reference_date))
    if not active:
        return None, None
    if len(active) == 1:
        return active[0], None

    normalized_texts = { " ".join(item.clause_text.split()) for item in active }
    if len(normalized_texts) == 1:
        selected = max(active, key=lambda item: (item.effective_from, item.version_id))
        return selected, None

    defined_precedence = [item for item in active if item.precedence is not None]
    if defined_precedence:
        highest = max(item.precedence for item in defined_precedence if item.precedence is not None)
        winners = [item for item in defined_precedence if item.precedence == highest]
        # Do not let an unranked version be silently overridden by a ranked one.
        has_unranked = any(item.precedence is None for item in active)
        if len(winners) == 1 and not has_unranked:
            return winners[0], None

    evidence = tuple(_evidence_for_version(item, selected=False) for item in active)
    result = ResolutionResult(
        obligation_id=obligation.obligation_id,
        outcome=Outcome.CONFLICT,
        reason="Multiple in-force versions have different text and no unique source-grounded precedence.",
        reference_date=reference_date,
        evidence=evidence,
    )
    return None, result


def _active_exemptions(version: ClauseVersion, reference_date: date) -> tuple[ExceptionRule, ...]:
    return tuple(rule for rule in version.exemptions if rule.is_active(reference_date))


def _exception_evidence(rule: ExceptionRule, evaluation: ConditionEvaluation) -> dict[str, Any]:
    return {
        "kind": "exemption_rule",
        "relation_id": rule.relation_id,
        "clause_id": rule.clause_id,
        "source_url": rule.official_url,
        "effect": rule.effect.value,
        "priority": rule.priority,
        "condition": list(evaluation.trace),
        "condition_value": evaluation.value.value,
    }


def _resolve_exception_effects(
    rules: tuple[ExceptionRule, ...],
    profile: dict[str, Any],
) -> tuple[Outcome | None, str, tuple[dict[str, Any], ...], tuple[str, ...], bool]:
    """Return final exception effect, reason, evidence, missing facts, and conflict."""
    evaluated = [(rule, evaluate_condition(rule.condition, profile)) for rule in rules]
    true_rules = [(rule, evaluation) for rule, evaluation in evaluated
                  if evaluation.value == TruthValue.TRUE]
    unknown_rules = [(rule, evaluation) for rule, evaluation in evaluated
                     if evaluation.value == TruthValue.UNKNOWN]
    evidence = tuple(_exception_evidence(rule, evaluation) for rule, evaluation in evaluated)
    missing = tuple(sorted({
        fact for _, evaluation in unknown_rules for fact in evaluation.missing_facts
    }))

    if not true_rules:
        if unknown_rules:
            return Outcome.INDETERMINATE, "An active exemption condition cannot be evaluated from known facts.", evidence, missing, False
        return None, "", evidence, (), False

    # Legal precedence must come from data. If the top relevant rules do not have
    # a unique, known rank, opposing effects are a conflict rather than a guess.
    priority_values = [rule.priority for rule, _ in true_rules]
    if any(priority is None for priority in priority_values):
        effects = {rule.effect for rule, _ in true_rules}
        if len(effects) > 1:
            return Outcome.CONFLICT, "Active exemption rules have opposing effects without documented priority.", evidence, missing, True
        top_rules = true_rules
    else:
        highest = max(priority for priority in priority_values if priority is not None)
        top_rules = [(rule, evaluation) for rule, evaluation in true_rules if rule.priority == highest]

    effects = {rule.effect for rule, _ in top_rules}
    if len(effects) > 1:
        return Outcome.CONFLICT, "Equal-priority active exemption rules have opposing effects.", evidence, missing, True
    effect = next(iter(effects))
    if effect == ExceptionEffect.EXEMPT:
        return Outcome.NOT_APPLICABLE, "An active exemption condition is true.", evidence, missing, False

    if unknown_rules:
        return Outcome.INDETERMINATE, "An active exemption condition is unresolved and could change the result.", evidence, missing, False
    return None, "No active exemption removes the obligation.", evidence, missing, False


def resolve_obligation(
    obligation_id: str,
    obligations: dict[str, Obligation],
    reference_date: date,
    entity_profile: dict[str, Any],
    policy: ResolverPolicy,
    _stack: tuple[str, ...] = (),
) -> ResolutionResult | None:
    """Resolve one obligation into an auditable outcome.

    Returns None only when the explicitly selected no-version policy is DROP.
    Cyclic dependencies and unresolved equally authoritative contradictions produce
    Conflict. The caller must preserve the exact ResolverPolicy used per run.
    """
    if obligation_id in _stack:
        cycle = (*_stack, obligation_id)
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.CONFLICT,
            reason=f"Dependency cycle detected: {' -> '.join(cycle)}.",
            reference_date=reference_date,
            evidence=({"kind": "dependency_cycle", "path": list(cycle)},),
        )

    obligation = obligations.get(obligation_id)
    if obligation is None:
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.INDETERMINATE,
            reason="The referenced obligation is not present in the loaded knowledge base.",
            reference_date=reference_date,
            missing_facts=(f"obligation:{obligation_id}",),
        )

    version, version_conflict = _resolve_version(obligation, reference_date)
    if version_conflict is not None:
        return version_conflict
    if version is None:
        if policy.no_version == NoVersionPolicy.DROP:
            return None
        evidence = tuple(_evidence_for_version(item, selected=False) for item in obligation.versions)
        evidence = ({"kind": "temporal_filter", "message": "No version is in force on the reference date."},) + evidence
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.NOT_APPLICABLE,
            reason="No recorded version of this obligation is in force on the reference date.",
            reference_date=reference_date,
            evidence=evidence,
        )

    evidence: list[dict[str, Any]] = [_evidence_for_version(version, selected=True)]
    applicability = evaluate_condition(version.applicability_condition, entity_profile)
    evidence.extend(applicability.trace)

    if (
        policy.missing_facts == MissingFactsPolicy.STRICT_MISSING
        and applicability.missing_facts
    ):
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.INDETERMINATE,
            reason="At least one fact required by the applicability rule is missing.",
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            missing_facts=applicability.missing_facts,
            evidence=tuple(evidence),
        )

    if applicability.value == TruthValue.FALSE:
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.NOT_APPLICABLE,
            reason="The entity profile does not satisfy the obligation's applicability condition.",
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            evidence=tuple(evidence),
        )

    if (
        applicability.value == TruthValue.UNKNOWN
        and policy.unknown_precedence == UnknownPrecedencePolicy.INDETERMINATE_FIRST
    ):
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.INDETERMINATE,
            reason="Applicability is unresolved before exception/dependency evaluation under the selected policy.",
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            missing_facts=applicability.missing_facts,
            evidence=tuple(evidence),
        )

    exceptions = _active_exemptions(version, reference_date)
    exception_outcome, exception_reason, exception_evidence, exception_missing, _ = (
        _resolve_exception_effects(exceptions, entity_profile)
    )
    evidence.extend(exception_evidence)
    if exception_outcome in {Outcome.NOT_APPLICABLE, Outcome.CONFLICT}:
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=exception_outcome,
            reason=exception_reason,
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            evidence=tuple(evidence),
        )

    dependency_results: list[ResolutionResult] = []
    for dependency in version.dependencies:
        if not dependency.is_active(reference_date):
            continue
        dependency_result = resolve_obligation(
            dependency.target_obligation_id,
            obligations,
            reference_date,
            entity_profile,
            policy,
            (*_stack, obligation_id),
        )
        evidence.append({
            "kind": "dependency",
            "relation_id": dependency.relation_id,
            "target_obligation_id": dependency.target_obligation_id,
            "clause_id": dependency.clause_id,
            "source_url": dependency.official_url,
            "active": True,
        })
        if dependency_result is None:
            dependency_result = ResolutionResult(
                obligation_id=dependency.target_obligation_id,
                outcome=Outcome.INDETERMINATE,
                reason="Dependency has no in-force version and was dropped under the selected temporal policy.",
                reference_date=reference_date,
                evidence=({"kind": "dependency_temporal_gap"},),
            )
        dependency_results.append(dependency_result)
        evidence.extend(dependency_result.evidence)

    for dependency_result in dependency_results:
        if dependency_result.outcome in {Outcome.CONFLICT, Outcome.NOT_APPLICABLE}:
            outcome = dependency_result.outcome
            reason = (
                f"Dependency {dependency_result.obligation_id} is conflicting."
                if outcome == Outcome.CONFLICT
                else f"Required dependency {dependency_result.obligation_id} is not applicable."
            )
            return ResolutionResult(
                obligation_id=obligation_id,
                outcome=outcome,
                reason=reason,
                reference_date=reference_date,
                version_id=version.version_id,
                clause_id=version.clause_id,
                source_url=version.official_url,
                evidence=tuple(evidence),
                dependency_results=tuple(dependency_results),
            )

    unresolved_facts = tuple(sorted(set(applicability.missing_facts) | set(exception_missing)))
    unresolved_dependencies = [
        result for result in dependency_results
        if result.outcome == Outcome.INDETERMINATE
    ]
    if exception_outcome == Outcome.INDETERMINATE or unresolved_dependencies:
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.INDETERMINATE,
            reason=(
                exception_reason
                if exception_outcome == Outcome.INDETERMINATE
                else "At least one required dependency is indeterminate."
            ),
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            missing_facts=unresolved_facts,
            evidence=tuple(evidence),
            dependency_results=tuple(dependency_results),
        )

    if applicability.value == TruthValue.UNKNOWN:
        return ResolutionResult(
            obligation_id=obligation_id,
            outcome=Outcome.INDETERMINATE,
            reason="The applicability condition remains UNKNOWN after definitive rules were checked.",
            reference_date=reference_date,
            version_id=version.version_id,
            clause_id=version.clause_id,
            source_url=version.official_url,
            missing_facts=unresolved_facts,
            evidence=tuple(evidence),
            dependency_results=tuple(dependency_results),
        )

    return ResolutionResult(
        obligation_id=obligation_id,
        outcome=Outcome.APPLICABLE,
        reason="The version is in force, the applicability condition is true, and no active exemption or failed dependency removes it.",
        reference_date=reference_date,
        version_id=version.version_id,
        clause_id=version.clause_id,
        source_url=version.official_url,
        evidence=tuple(evidence),
        dependency_results=tuple(dependency_results),
    )
