"""Typed domain records for TAARR's deterministic resolution layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, TypeAlias

Condition: TypeAlias = dict[str, Any]


class Outcome(StrEnum):
    APPLICABLE = "Applicable"
    NOT_APPLICABLE = "Not applicable"
    INDETERMINATE = "Indeterminate"
    CONFLICT = "Conflict"


class TruthValue(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class ExceptionEffect(StrEnum):
    EXEMPT = "EXEMPT"
    NOT_EXEMPT = "NOT_EXEMPT"


class NoVersionPolicy(StrEnum):
    DROP = "DROP"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MissingFactsPolicy(StrEnum):
    STRICT_MISSING = "STRICT_MISSING"
    KLEENE = "KLEENE"


class UnknownPrecedencePolicy(StrEnum):
    INDETERMINATE_FIRST = "INDETERMINATE_FIRST"
    DEFINITIVE_RULES_FIRST = "DEFINITIVE_RULES_FIRST"


@dataclass(frozen=True, slots=True)
class ResolverPolicy:
    """Explicit policy choices for algorithm ambiguities in the project documents.

    These have no defaults by design: callers must select and record them.
    """

    no_version: NoVersionPolicy
    missing_facts: MissingFactsPolicy
    unknown_precedence: UnknownPrecedencePolicy


@dataclass(frozen=True, slots=True)
class ExceptionRule:
    relation_id: str
    clause_id: str
    official_url: str
    condition: Condition
    effect: ExceptionEffect
    effective_from: date
    effective_to: date | None = None
    priority: int | None = None

    def is_active(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (
            self.effective_to is None or on_date < self.effective_to
        )


@dataclass(frozen=True, slots=True)
class DependencyRule:
    relation_id: str
    target_obligation_id: str
    clause_id: str
    official_url: str
    effective_from: date | None = None
    effective_to: date | None = None

    def is_active(self, on_date: date) -> bool:
        return (
            (self.effective_from is None or self.effective_from <= on_date)
            and (self.effective_to is None or on_date < self.effective_to)
        )


@dataclass(frozen=True, slots=True)
class ClauseVersion:
    obligation_id: str
    version_id: str
    clause_id: str
    official_url: str
    clause_text: str
    effective_from: date
    effective_to: date | None
    applicability_condition: Condition
    exemptions: tuple[ExceptionRule, ...] = ()
    dependencies: tuple[DependencyRule, ...] = ()
    precedence: int | None = None

    def is_active(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (
            self.effective_to is None or on_date < self.effective_to
        )


@dataclass(frozen=True, slots=True)
class Obligation:
    obligation_id: str
    versions: tuple[ClauseVersion, ...]


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    value: TruthValue
    missing_facts: tuple[str, ...] = ()
    trace: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    obligation_id: str
    outcome: Outcome
    reason: str
    reference_date: date
    version_id: str | None = None
    clause_id: str | None = None
    source_url: str | None = None
    missing_facts: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    dependency_results: tuple[ResolutionResult, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable result with nested dependency evidence."""
        return {
            "obligation_id": self.obligation_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "reference_date": self.reference_date.isoformat(),
            "version_id": self.version_id,
            "clause_id": self.clause_id,
            "source_url": self.source_url,
            "missing_facts": list(self.missing_facts),
            "evidence": list(self.evidence),
            "dependencies": [result.to_dict() for result in self.dependency_results],
        }
