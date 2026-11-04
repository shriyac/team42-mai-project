"""Shared typed state for the LAGA LangGraph workflow."""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict

from tools.fee_calculator import FeeCalculationResult


class EvidenceBundle(TypedDict, total=False):
    subquestion: str
    query: str
    documents: list[Any]
    error: str


class AnswerPart(TypedDict, total=False):
    subquestion: str
    answer: str
    source_ids: list[str]
    error: str


class LAGAState(TypedDict, total=False):
    """Request and orchestration state.

    ``tenant_id``, ``tenant_name``, and ``lease_id`` must come from trusted
    authentication and lease-ownership checks, never directly from request
    JSON. ``retrieved_evidence`` contains only evidence verified for that scope.
    """

    question: str
    tenant_id: str
    tenant_name: str
    lease_id: str
    as_of: str | date
    subquestions: list[str]
    fee_required: bool
    retrieved_evidence: list[EvidenceBundle]
    calculation: FeeCalculationResult | None
    calculations: list[dict[str, Any]]
    answer_parts: list[AnswerPart]
    answer: str
    citations: list[dict[str, Any]]
    validation_status: str
    validation_errors: list[str]
    input_errors: list[str]
    fee_errors: list[str]
    retry_count: int
    retry_subquestions: list[str]
    retry_queries: dict[str, str]
    tool_activity: list[dict[str, str]]
