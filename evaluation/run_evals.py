"""Reproducible graph evaluations. Mock mode must run via the isolated launcher.

    node scripts/run-isolated-tests.mjs evals
    PYTHONPATH=src:. .pythonlibs/bin/python -m evaluation.run_evals --mode live

Live mode never changes flags, bindings, snapshots, or database contents.
"""
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter

from agent.graph import build_graph
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
    required = {"question_id", "question", "tenant_id", "lease_id", "expected_answer",
                "expected_chunk_ids", "expected_tools", "expected_behavior", "annotation_status"}
    if dataset.get("schema_version") != 1 or len(cases) != 15:
        raise ValueError("Expected the versioned 15-question dataset.")
    if len({c["question_id"] for c in cases}) != 15:
        raise ValueError("Question IDs must be unique.")
    for case in cases:
        if not required <= case.keys():
            raise ValueError("Incomplete golden case.")
        if case["annotation_status"] not in {"verified", "needs_annotation"}:
            raise ValueError("Invalid annotation status.")
    return dataset


def live_backend():
    """Preflight genuine ownership/provenance before permitting service clients."""
    if not activation_requested():
        return None, "BLOCKED: live retrieval is disabled."
    try:
        config = load_configuration()
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
    outcome = {"question_id": case["question_id"], "category": case["category"],
               "expected_behavior": case["expected_behavior"]}
    try:
        principal, org, lease = backend.authorize(case["tenant_id"], case["lease_id"])
    except APIError as error:
        valid = case["expected_behavior"] == "deny" and error.status in {403, 404}
        return {**outcome, "status": "PASSED" if valid else "FAILED", "executed": True,
                "actual_answer": "", "citations": [], "retrieved_chunks": [],
                "retrieval_trace": [], "tools": [], "calculations": [],
                "checks": {"authorization": valid, "tools": case["expected_tools"] == []},
                "error_code": error.code, "latency_seconds": perf_counter() - start}
    try:
        factory = factory_builder(principal, org, lease)
    except RAGIntegrationError as error:
        return {**outcome, "status": "NOT_RUN", "executed": False,
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
        "validation_errors": state.get("validation_errors", []),
        "fee_errors": state.get("fee_errors", []), "citations": state.get("citations", []),
        "calculations": state.get("calculations", []), "calculator_calls": calculator_calls,
        "tools": (["retrieval"] if traced.trace else []) + (["fee_calculator"] if calculator_calls else []),
        "tool_activity": state.get("tool_activity", []), "retrieved_chunks": list(retrieved.values()),
        "retrieval_trace": [{"query": e["query"], "chunk_ids": [d.metadata["chunk_id"] for d in e["documents"]],
                             "error": e.get("error")} for e in traced.trace],
        "top_five_chunk_ids": top_five(traced.trace),
        "retrieval_scores": retrieval_scores(case["expected_chunk_ids"], top_five(traced.trace)),
        "checks": checks, "latency_seconds": perf_counter() - start,
    }


def summarize(outcomes):
    executed = [o for o in outcomes if o["executed"]]
    summary = {s.lower(): sum(o["status"] == s for o in outcomes)
               for s in ("PASSED", "FAILED", "NOT_RUN")}
    summary["questions_executed"] = len(executed)
    metrics = {}
    for name, key in (("tool_selection_accuracy", "tools"), ("calculation_exact_match", "calculation"),
                      ("citation_correctness", "citations"), ("groundedness_structural", "groundedness"),
                      ("abstention_clarification_correctness", "abstention"),
                      ("authorization_correctness", "authorization")):
        values = [o["checks"][key] for o in executed if o.get("checks", {}).get(key) is not None]
        metrics[name] = {"passed": sum(values), "denominator": len(values),
                         "value": sum(values) / len(values) if values else None}
    retrieval = [o["retrieval_scores"] for o in executed if o.get("retrieval_scores") is not None]
    for key in ("recall_at_5", "precision_at_5"):
        metrics[key] = {"value": mean(r[key] for r in retrieval) if retrieval else None,
                        "denominator": len(retrieval)}
    times = [o["latency_seconds"] for o in executed]
    metrics["latency_seconds"] = {"average": mean(times) if times else None,
                                  "median": median(times) if times else None, "denominator": len(times)}
    return {**summary, "metrics": metrics}


def evaluate(mode, dataset=None):
    dataset = dataset or load_dataset()
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
            backend, reason = live_backend()

            def factory_builder(principal, org, lease):
                return ProductionRetrieverFactory(backend).for_authorized_lease(
                    principal=principal, organization_id=org, lease=lease,
                )
        outcomes = []
        for case in dataset["cases"]:
            blocked = reason or ("needs_annotation" if case["annotation_status"] != "verified" else None)
            if blocked:
                outcomes.append({"question_id": case["question_id"], "category": case["category"],
                                 "status": "NOT_RUN", "executed": False, "reason": blocked})
            else:
                outcomes.append(execute_case(case, backend, factory_builder))
    return {"mode": mode, "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_source": dataset["source"], "summary": summarize(outcomes), "outcomes": outcomes}


LIMITATIONS = """All assertions are deterministic automated checks; no LLM judge or confidence score is used.
Golden reference assertions were agent-authored from the synthetic unsigned PDF; unknown references must be marked
needs_annotation. No independent legal or end-to-end human answer-quality review was performed.
Mock retrieval uses transparent topic rules, NOT Pinecone or embeddings; its scores are fixture diagnostics,
not live RAG performance. The authorization denial uses real backend ownership methods against a disposable
SQLite fixture in mock mode, not an authenticated browser/session test.
Recall@5 and Precision@5 use the first five unique chunks in first-seen subquestion/retry order.
Scores are macro-averaged over executed cases with nonempty reference chunk annotations; Precision@5 always
divides by five, including empty slots. Reference sets are selected, not exhaustive: precision is provisional
against those annotations. Repeated retries are captured but are not counted as independent questions.
Citation correctness compares source metadata, scope, references and literal quotes against returned evidence.
Groundedness is structural excerpt support only, NOT semantic entailment or legal correctness; fee arithmetic
is checked separately with Decimal. Clarification uses an explicit abstention/uncertainty lexical check.
Answer references use stated substring assertions, not full natural-language equivalence.
Latency includes per-case authorization, graph compilation, retrieval/retries and tools; excludes corpus
preparation and global live preflight. No live provider latency is claimed for mock runs.
Disabled/unverified live runs are NOT_RUN / BLOCKED, never PASSED. Missing-annotation cases are NOT_RUN.
No snapshot/binding approval, re-ingestion, flag changes, or application code rewrites are performed."""


def save_reports(result, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results.json"
    previous = json.loads(path.read_text()) if path.is_file() else {"schema_version": 1, "runs": {}}
    previous["runs"][result["mode"]] = result
    path.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + "\n")
    lines = ["# LAGA MVP evaluation report", "", "## Method and limitations", "", LIMITATIONS, ""]
    for mode, run in previous["runs"].items():
        s = run["summary"]
        lines += [f"## {mode.upper()} evaluation", "", f"Generated (UTC): {run['generated_at']}", "",
                  f"Questions executed: **{s['questions_executed']}/15**. "
                  f"Passed: **{s['passed']}**; failed: **{s['failed']}**; not run: **{s['not_run']}**.", "",
                  "| Metric | Result | Denominator |", "|---|---:|---:|"]
        for name, metric in s["metrics"].items():
            value = metric.get("value")
            display = "N/A" if value is None else f"{value:.4f}"
            if name == "latency_seconds":
                display = (f"average {metric['average']:.6f}s; median {metric['median']:.6f}s"
                           if metric["average"] is not None else "N/A")
            if "passed" in metric:
                display += f" ({metric['passed']}/{metric['denominator']})"
            lines.append(f"| {name} | {display} | {metric['denominator']} |")
        lines += ["", "### Per-question outcomes and failure examples", ""]
        for outcome in run["outcomes"]:
            failed = [k for k, v in outcome.get("checks", {}).items() if v is False]
            detail = outcome.get("reason") or (", ".join(failed) if failed else "Assertions passed.")
            lines.append(f"- `{outcome['question_id']}` — **{outcome['status']}**: {detail}")
            if outcome["status"] == "FAILED":
                lines.append("  - Actual answer: " + outcome.get("actual_answer", "").replace("\n", " "))
                if outcome.get("fee_errors"):
                    lines.append("  - Fee extraction errors: " + "; ".join(outcome["fee_errors"]))
        lines += [""]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation")
    args = parser.parse_args()
    try:
        result = evaluate(args.mode, load_dataset(args.dataset))
        save_reports(result, args.output_dir)
    except Exception:
        # Never echo exception objects, SDK bodies, environment, or credentials.
        print("Evaluation could not complete. Check dataset/source availability and use the documented launcher.")
        return 2
    s = result["summary"]
    print(f"{args.mode.upper()}: {s['questions_executed']} executed; {s['passed']} passed; "
          f"{s['failed']} failed; {s['not_run']} NOT_RUN.")
    # Findings are not runner crashes. -- fail based on the detailed report.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
