"""Reproducible graph evaluations. Mock mode must run via the isolated launcher.

    node scripts/run-isolated-tests.mjs evals
    PYTHONPATH=src:. .pythonlibs/bin/python -m evaluation.run_evals --mode live

Live mode never changes flags, bindings, snapshots, or database contents.
"""
from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter

from agent.graph import build_graph
from agent.evidence import citation_from_document
from laga.assistant_adapter import adapt_answer
from laga.backend_api import APIError
from laga.rag_configuration import RAGIntegrationError, activation_requested, load_configuration
from laga.rag_integration import ProductionRetrieverFactory
from laga.rag_mapping import verify_scope
from tools.fee_calculator import calculate_late_fee

from .fixtures import ROOT, FixtureFactory, ReadOnlyBackend, canonical_documents, mock_backend
from .metrics import assess, retrieval_scores, top_five

DATASET = Path(__file__).with_name("golden_questions.json")


def load_dataset(path=DATASET):
    dataset = json.loads(Path(path).read_text())
    cases = dataset["cases"]
    required = {
        "id", "question_id", "category", "question", "tenant_id", "lease_id",
        "expected_answer", "expected_key_facts", "expected_document_ids",
        "expected_chunk_ids", "expected_tools", "expected_behavior",
        "expected_status", "annotation_status", "supporting_evidence",
    }
    if dataset.get("schema_version") != 1 or len(cases) != 10:
        raise ValueError("Expected the versioned 10-question dataset.")
    if len({c["question_id"] for c in cases}) != len(cases):
        raise ValueError("Question IDs must be unique.")
    for case in cases:
        if not required <= case.keys():
            raise ValueError("Incomplete golden case.")
        if case["annotation_status"] not in {"verified", "needs_annotation"}:
            raise ValueError("Invalid annotation status.")
        if case["id"] != case["question_id"]:
            raise ValueError("Case ID aliases must agree.")
        for key in ("id", "question", "tenant_id", "lease_id", "expected_answer"):
            if not isinstance(case[key], str) or not case[key].strip():
                raise ValueError("Golden identifiers and expectations must be nonempty.")
        for key in ("expected_key_facts", "expected_document_ids", "expected_chunk_ids", "expected_tools"):
            values = case[key]
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError("Golden annotation lists must contain nonempty strings.")
            if len(values) != len(set(values)):
                raise ValueError("Golden annotation lists must not contain duplicates.")
        if not case["expected_key_facts"]:
            raise ValueError("Each case requires expected key facts or safety expectations.")
        statuses = {"answer": "supported", "calculation": "supported",
                    "clarification": "needs_clarification", "abstain": "needs_clarification",
                    "deny": "denied"}
        if statuses.get(case["expected_behavior"]) != case["expected_status"]:
            raise ValueError("Expected behavior and status disagree.")
        if not set(case["expected_tools"]) <= {"retrieval", "fee_calculator"}:
            raise ValueError("Unknown expected tool.")
        if case["annotation_status"] == "verified":
            evidence = case["supporting_evidence"]
            if not isinstance(evidence, list) or {
                item.get("chunk_id") for item in evidence if isinstance(item, dict)
            } != set(case["expected_chunk_ids"]):
                raise ValueError("Verified reference chunks require complete evidence mappings.")
            for item in evidence:
                if (
                    not isinstance(item, dict)
                    or not all(isinstance(item.get(k), str) and item[k].strip()
                               for k in ("chunk_id", "clause", "quote"))
                    or type(item.get("page")) is not int or item["page"] < 1
                ):
                    raise ValueError("Evidence requires an exact quote, clause and positive PDF page.")
            if case["expected_behavior"] in {"answer", "calculation"} and (
                not evidence or not case["expected_document_ids"]
            ):
                raise ValueError("Verified substantive answers require source evidence.")
            if not evidence and not case.get("verification_method"):
                raise ValueError("Negative cases require an explicit verification method.")
    return dataset


def live_backend(configuration=None):
    """Preflight genuine ownership/provenance before permitting service clients."""
    if configuration is None and not activation_requested():
        return None, "BLOCKED: live retrieval is disabled."
    try:
        config = configuration or load_configuration()
        # Match the existing API startup path without opening a writable DB.
        from laga.paths import resolve_project_path
        database = resolve_project_path(os.environ.get("LAGA_DATABASE") or "data/backend.sqlite3")
        if not database.is_file():
            return None, "BLOCKED: the authorized backend database is unavailable."
        backend = ReadOnlyBackend(database)
        principal, _, _ = backend.authorize("tenant-1", "lease-1")
        verify_scope(backend, config, principal["id"], principal["name"], "lease-1")
        return backend, None
    except RAGIntegrationError as error:
        return None, "BLOCKED: " + error.code + " (production validation did not pass)."
    except (APIError, OSError, sqlite3.Error, ValueError):
        return None, "BLOCKED: authoritative local evidence/ownership could not be verified."


class TracedFactory:
    def __init__(self, delegate):
        self.delegate, self.trace = delegate, []

    def __call__(self, **scope):
        retriever = self.delegate(**scope)
        outer = self

        class TracedRetriever:
            def invoke(self, query):
                try:
                    documents = list(retriever.invoke(query))
                except Exception:
                    outer.trace.append({"query": query, "documents": [], "error": "RETRIEVAL_FAILED"})
                    raise
                outer.trace.append({"query": query, "documents": documents})
                return documents

        return TracedRetriever()


def execute_case(case, backend, factory_builder):
    start = perf_counter()
    outcome = {"question_id": case["question_id"], "question": case["question"], "category": case["category"],
               "expected_behavior": case["expected_behavior"]}
    try:
        if case["expected_behavior"] == "deny":
            # Exercise the actual backend API method, not an LLM denial or just
            # the evaluation helper. Ownership is checked before assistant use.
            backend.post_assistant_messages(
                user={"id": case["tenant_id"]}, question=case["question"],
                scope={"type": "lease", "id": case["lease_id"]},
                asOf="2026-11-06",
            )
            return {
                **outcome, "status": "FAILED", "executed": True,
                "response_status": "unexpected_authorization", "actual_answer": "",
                "citations": [], "retrieved_chunks": [], "actual_tool_calls": [],
                "retrieval_trace": [], "tools": [], "calculations": [],
                "checks": {"authorization": False}, "failure_reasons": ["authorization"],
                "latency_seconds": perf_counter() - start,
            }
        principal, org, lease = backend.authorize(case["tenant_id"], case["lease_id"])
    except APIError as error:
        valid = case["expected_behavior"] == "deny" and error.status in {403, 404}
        return {**outcome, "status": "PASSED" if valid else "FAILED", "executed": True,
                "actual_answer": "", "response_status": "denied" if valid else "error",
                "citations": [], "retrieved_chunks": [], "actual_tool_calls": [],
                "retrieval_trace": [], "tools": [], "calculations": [],
                "checks": {"authorization": valid, "tools": case["expected_tools"] == []},
                "error_code": error.code, "http_equivalent_status": error.status,
                "authorization_interface": "BackendAPI.post_assistant_messages" if valid else "backend authorization",
                "failure_reasons": [] if valid else ["authorization"],
                "rubric_review": {"method": "Real backend authorization boundary",
                                  "criteria": {"foreign_lease_denied_before_retrieval": valid}},
                "latency_seconds": perf_counter() - start}
    try:
        factory = factory_builder(principal, org, lease)
    except RAGIntegrationError as error:
        return {**outcome, "status": "NOT_RUN", "executed": False, "blocked": True,
                "reason": "BLOCKED: " + error.code + " (production preflight failed)."}
    traced = TracedFactory(factory)
    calculator_calls = []

    def calculator(inputs):
        result = calculate_late_fee(inputs)
        calculator_calls.append({"inputs": result.to_dict()["inputs"], "result": result.to_dict()})
        return result

    state = build_graph(retriever_factory=traced, fee_calculator=calculator).invoke({
        "question": case["question"], "tenant_id": principal["id"],
        "tenant_name": principal["name"], "lease_id": lease["id"], "as_of": "2026-11-06",
    })
    # The graph deliberately swallows retrieval errors into abstention. For live
    # evaluation, inspect the production adapter's recorded failure as well.
    if hasattr(factory, "check_failure"):
        try:
            factory.check_failure()
        except RAGIntegrationError as error:
            return {**outcome, "status": "FAILED", "executed": True,
                    "checks": {"production_retrieval": False}, "error_code": error.code,
                    "actual_answer": state.get("answer", ""),
                    "latency_seconds": perf_counter() - start}
    checks = assess(case, state, traced.trace, calculator_calls)
    # Obtain the actual public status and DTO from the existing adapter, not
    # a guessed mapping. This is still a direct service evaluation, not HTTP.
    evidence = []
    for event in traced.trace:
        for doc in event["documents"]:
            record = citation_from_document(doc, "S0")
            if record:
                clause = record["clause_id"]
                title = doc.metadata.get("section_title", "")
                evidence.append({
                    "identity": {k: v for k, v in record.items() if k != "source_id"},
                    "source_spans": doc.metadata.get("source_spans", []),
                    "section": f"{clause} — {title}" if title and clause != title else clause or title,
                })
    response = None
    try:
        response = adapt_answer(state, thread_id="evaluation-" + case["id"], evidence=evidence)
        backend._validate("Answer", response)
        checks["response_dto"] = True
        checks["response_status"] = response["status"] == case["expected_status"]
    except Exception:
        checks["response_dto"] = False
        checks["response_status"] = False
    if case["expected_behavior"] == "deny":
        # An authorization test that reached the graph can never pass.
        checks["authorization"] = False
    if any(e.get("error") for e in traced.trace):
        checks["retrieval_execution"] = False
    retrieved = {}
    for event in traced.trace:
        for doc in event["documents"]:
            retrieved.setdefault(doc.metadata["chunk_id"], {
                "chunk_id": doc.metadata["chunk_id"], "page_content": doc.page_content,
                "metadata": doc.metadata,
            })
    return {
        **outcome, "status": "FAILED" if False in checks.values() else "PASSED", "executed": True,
        "actual_answer": state.get("answer", ""), "validation_status": state.get("validation_status"),
        "response_status": response["status"] if response else "invalid_response",
        "response_status_origin": "Existing adapt_answer() plus BackendAPI Answer schema validation; not HTTP.",
        "public_response": response,
        "validation_errors": state.get("validation_errors", []),
        "fee_errors": state.get("fee_errors", []), "citations": state.get("citations", []),
        "calculations": state.get("calculations", []), "calculator_calls": calculator_calls,
        "tools": (["retrieval"] if traced.trace else []) + (["fee_calculator"] if calculator_calls else []),
        "tool_activity": state.get("tool_activity", []), "retrieved_chunks": list(retrieved.values()),
        "actual_tool_calls": [
            {"tool": "retrieval", "query": e["query"], "result_count": len(e["documents"]),
             "error": e.get("error")} for e in traced.trace
        ] + [{"tool": "fee_calculator", **call} for call in calculator_calls],
        "retrieval_trace": [{"query": e["query"], "chunk_ids": [d.metadata["chunk_id"] for d in e["documents"]],
                             "error": e.get("error")} for e in traced.trace],
        "top_five_chunk_ids": top_five(traced.trace),
        "retrieval_scores": retrieval_scores(case["expected_chunk_ids"], top_five(traced.trace)),
        "retrieval_measurement_status": (
            "MEASURED" if case["expected_chunk_ids"] else "NOT_MEASURED"
        ),
        "checks": checks, "latency_seconds": perf_counter() - start,
        "failure_reasons": [key for key, value in checks.items() if value is False],
        "rubric_review": {
            "method": "Explicit deterministic source/required-fact rubric; no model self-scoring.",
            "criteria": {k: checks.get(k) for k in (
                "answer_reference", "reference_evidence_coverage", "returned_citations",
                "factual_support", "abstention", "response_status",
            )},
        },
    }


def summarize(outcomes):
    executed = [o for o in outcomes if o["executed"]]
    summary = {s.lower(): sum(o["status"] == s for o in outcomes)
               for s in ("PASSED", "FAILED", "NOT_RUN")}
    summary["questions_executed"] = len(executed)
    summary["total_cases"] = len(outcomes)
    summary["blocked"] = sum(bool(o.get("blocked")) for o in outcomes)
    metrics = {}
    for name, key in (("tool_selection_accuracy", "tools"), ("calculation_exact_match", "calculation"),
                      ("citation_correctness", "citations"), ("groundedness_structural", "groundedness"),
                      ("returned_citation_correctness", "returned_citations"),
                      ("answer_factual_support_rubric", "factual_support"),
                      ("abstention_clarification_correctness", "abstention"),
                      ("authorization_correctness", "authorization")):
        values = [o["checks"][key] for o in executed if o.get("checks", {}).get(key) is not None]
        metrics[name] = {"passed": sum(values), "denominator": len(values),
                         "value": sum(values) / len(values) if values else None,
                         "measurement_status": "MEASURED" if values else "NOT_MEASURED"}
    retrieval = [o["retrieval_scores"] for o in executed if o.get("retrieval_scores") is not None]
    for key in ("recall_at_5", "precision_at_5"):
        metrics[key] = {"value": mean(r[key] for r in retrieval) if retrieval else None,
                        "denominator": len(retrieval),
                        "measurement_status": "MEASURED" if retrieval else "NOT_MEASURED"}
    metrics["overall_case_pass_rate"] = {
        "value": summary["passed"] / len(outcomes) if outcomes else None,
        "passed": summary["passed"], "denominator": len(outcomes),
    }
    times = [o["latency_seconds"] for o in executed]
    metrics["latency_seconds"] = {"average": mean(times) if times else None,
                                  "median": median(times) if times else None, "denominator": len(times)}
    return {**summary, "metrics": metrics}


def evaluate(mode, dataset=None, *, live_configuration=None):
    dataset = dataset or load_dataset()
    if mode == "offline":
        mode = "mock"
    if mode not in {"mock", "live"}:
        raise ValueError("Mode must be mock or live.")
    if mode == "mock" and os.environ.get("LAGA_TEST_ISOLATED") != "1":
        raise RuntimeError("Use node scripts/run-isolated-tests.mjs evals for secret-isolated mock evaluation.")
    with TemporaryDirectory(prefix="laga-eval-") as directory:
        # Loading/chunking the public fixture performs no ingestion or API calls.
        documents = canonical_documents(dataset["source"])
        known = {d.metadata["chunk_id"] for d in documents}
        for case in dataset["cases"]:
            if case["annotation_status"] == "verified" and not set(case["expected_chunk_ids"]) <= known:
                raise ValueError("Unknown reference chunk; re-annotation required.")
        if mode == "mock":
            backend, reason = mock_backend(directory), None

            def factory_builder(principal, org, lease):
                return FixtureFactory(documents, (principal["id"], principal["name"], lease["id"]))
        else:
            backend, reason = live_backend(live_configuration)
            if live_configuration is not None and (
                not live_configuration.synthetic_demo_enabled
                or live_configuration.expected_corpus_id != dataset["source"]["corpus_id"]
            ):
                backend, reason = None, "BLOCKED: isolated demo configuration/corpus pin is not approved."

            def factory_builder(principal, org, lease):
                return ProductionRetrieverFactory(
                    backend, configuration_loader=(lambda: live_configuration)
                    if live_configuration is not None else load_configuration,
                ).for_authorized_lease(
                    principal=principal, organization_id=org, lease=lease,
                )
        outcomes = []
        for case in dataset["cases"]:
            blocked = reason or ("needs_annotation" if case["annotation_status"] != "verified" else None)
            if blocked:
                outcomes.append({"question_id": case["question_id"], "category": case["category"],
                                 "status": "NOT_RUN", "executed": False,
                                 "blocked": bool(reason), "reason": blocked})
            else:
                outcomes.append(execute_case(case, backend, factory_builder))
    return {"mode": mode, "execution_mode": "OFFLINE" if mode == "mock" else "LIVE",
            "dataset_fingerprint": sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_source": dataset["source"], "summary": summarize(outcomes), "outcomes": outcomes}


LIMITATIONS = """All assertions are deterministic automated checks; no LLM judge or confidence score is used.
Golden reference assertions were agent-authored from the synthetic unsigned PDF; unknown references must be marked
needs_annotation. No independent legal or end-to-end human answer-quality review was performed.
Mock retrieval uses transparent topic rules, NOT Pinecone or embeddings; its scores are fixture diagnostics,
not live RAG performance. The authorization denial uses real backend ownership methods against a disposable
SQLite fixture in mock mode, not an authenticated browser/session test.
An OFFLINE run does not activate retrieval or constitute a new LIVE evaluation.
Recall@5 and Precision@5 use the first five unique chunks in first-seen subquestion/retry order.
Scores are macro-averaged over executed cases with nonempty reference chunk annotations; Precision@5 always
divides by five, including empty slots. Reference sets are selected, not exhaustive: precision is provisional
against those annotations. Repeated retries are captured but are not counted as independent questions.
Citation correctness compares source metadata, scope, references and literal quotes against returned evidence.
Groundedness is structural excerpt support only, NOT semantic entailment or legal correctness; fee arithmetic
is checked separately with Decimal. Clarification requires abstention with no citations or calculation.
Factual support uses an explicit rubric: required annotated answer fragments, canonical citation provenance,
and required-source coverage. This is automated evidence-based review, not model confidence or an independent
human semantic/legal assessment. Legitimate alternative passages can fail selected-chunk coverage.
Answer references use stated substring assertions, not full natural-language equivalence.
Latency includes per-case authorization, graph compilation, retrieval/retries and tools; excludes corpus
preparation and global live preflight. No live provider latency is claimed for mock runs.
Disabled/unverified live runs are NOT_RUN / BLOCKED, never PASSED. Missing-annotation cases are NOT_RUN.
An explicit isolated-demo run uses an in-memory configuration only; application flags stay unchanged.
The public response status comes from the existing backend adapter and schema; Q10 calls the actual
BackendAPI.post_assistant_messages method, but this is not an authenticated HTTP/browser test.
Q06/Q07 currently require clarification; their conditional reference is not a mandatory calculator call.
Calculation exact-match is NOT_MEASURED when no case expects a numeric calculation.
No snapshot/binding approval, re-ingestion, persistent flag changes, or application code rewrites are performed."""


def save_reports(result, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results.json"
    previous = json.loads(path.read_text()) if path.is_file() else {"schema_version": 1, "runs": {}}
    # Never mix old findings from another dataset with the current release run.
    previous["runs"] = {k: v for k, v in previous.get("runs", {}).items()
                        if v.get("dataset_fingerprint") == result["dataset_fingerprint"]}
    previous["runs"][result["mode"]] = result
    path.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + "\n")
    lines = ["# LAGA MVP evaluation report", "", "## Method and limitations", "", LIMITATIONS, ""]
    for mode, run in previous["runs"].items():
        s = run["summary"]
        label = run.get("execution_mode", mode.upper())
        lines += [f"## {label} evaluation", "", f"Generated (UTC): {run['generated_at']}", "",
                  f"Questions executed: **{s['questions_executed']}/{s['total_cases']}**. "
                  f"Passed: **{s['passed']}**; failed: **{s['failed']}**; not run: **{s['not_run']}**; "
                  f"blocked: **{s['blocked']}** (subset of not run).", "",
                  "| Metric | Result | Denominator |", "|---|---:|---:|"]
        for name, metric in s["metrics"].items():
            value = metric.get("value")
            display = "NOT_MEASURED" if value is None else f"{value:.4f}"
            if name == "latency_seconds":
                display = (f"average {metric['average']:.6f}s; median {metric['median']:.6f}s"
                           if metric["average"] is not None else "N/A")
            if "passed" in metric:
                display += f" ({metric['passed']}/{metric['denominator']})"
            lines.append(f"| {name} | {display} | {metric['denominator']} |")
        lines += ["", "Cases with no ground-truth chunks: Recall@5 is **NOT_MEASURED**, "
                  "not zero or a guessed score. Citation correctness includes expected "
                  "answer/calculation cases with missing citations as failures. "
                  "Returned-citation correctness scores only cases that actually returned citations.", ""]
        lines += ["", "### Per-question outcomes and failure examples", ""]
        for outcome in run["outcomes"]:
            failed = [k for k, v in outcome.get("checks", {}).items() if v is False]
            detail = outcome.get("reason") or (", ".join(failed) if failed else "Assertions passed.")
            lines.append(f"- `{outcome['question_id']}` — **{outcome['status']}**: {detail}")
            if outcome.get("response_status"):
                lines.append(f"  - Response status: `{outcome['response_status']}`; "
                             f"latency: {outcome['latency_seconds']:.6f}s; "
                             f"tools: {', '.join(outcome.get('tools', [])) or 'none'}.")
            if outcome["status"] == "FAILED":
                lines.append("  - Actual answer: " + outcome.get("actual_answer", "").replace("\n", " "))
                if outcome.get("fee_errors"):
                    lines.append("  - Fee extraction errors: " + "; ".join(outcome["fee_errors"]))
                if outcome.get("validation_errors"):
                    lines.append("  - Validation errors: " + "; ".join(outcome["validation_errors"]))
        lines += [""]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "mock", "live"), required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation")
    parser.add_argument("--isolated-demo", action="store_true",
                        help="LIVE only: enable reviewed demo flags in memory, never in the application.")
    args = parser.parse_args()
    try:
        if args.isolated_demo and args.mode != "live":
            raise ValueError("The isolated demo option requires live mode.")
        config = None
        if args.isolated_demo:
            config = load_configuration({
                **os.environ, "LAGA_RAG_ENABLED": "true",
                "LAGA_RAG_SYNTHETIC_DEMO_ENABLED": "true",
            })
        result = evaluate(args.mode, load_dataset(args.dataset), live_configuration=config)
        save_reports(result, args.output_dir)
    except Exception:
        # Never echo exception objects, SDK bodies, environment, or credentials.
        print("Evaluation could not complete. Check dataset/source availability and use the documented launcher.")
        return 2
    s = result["summary"]
    print(f"{result['execution_mode']}: {s['questions_executed']} executed; {s['passed']} passed; "
          f"{s['failed']} failed; {s['not_run']} NOT_RUN.")
    # Findings are not runner crashes. -- fail based on the detailed report.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
