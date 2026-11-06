"""Run independently: tenant-scoped hybrid retrieval -> top-k evidence -> LLM answer."""
import argparse
import json
from pathlib import Path

from lease_rag.config import Settings
from lease_rag.retrieval import TenantHybridRetriever, authorized_scope, generate_answer, load_snapshot
from lease_rag.storage import ACTIVE_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tenant-name', required=True, help='Trusted tenant identity, not extracted from the question.')
    parser.add_argument('--question', required=True)
    parser.add_argument('--document-id', action='append', help='Optional tenant lease ID; repeat for multiple leases.')
    parser.add_argument('--top-k', type=int, default=6)
    parser.add_argument('--fetch-k', type=int, default=24, help='Candidates per search before rank fusion.')
    parser.add_argument('--dense-weight', type=float, default=0.5)
    parser.add_argument('--env', type=Path)
    parser.add_argument('--active-file', type=Path, default=ACTIVE_PATH)
    parser.add_argument('--retrieve-only', action='store_true', help='Return evidence without calling the generation model.')
    parser.add_argument('--json', action='store_true', help='Print answer and full citation metadata as JSON.')
    args = parser.parse_args()
    settings = Settings.load(args.env)
    snapshot = load_snapshot(settings, args.active_file)
    authorized_scope(snapshot, args.tenant_name, args.document_id)
    pc, embeddings = settings.clients()
    retriever = TenantHybridRetriever(
        dense_index=pc.Index(snapshot['dense_index']), sparse_index=pc.Index(snapshot['sparse_index']),
        embeddings=embeddings, pc=pc, snapshot=snapshot, tenant_name=args.tenant_name,
        document_ids=args.document_id, k=args.top_k, fetch_k=args.fetch_k, dense_weight=args.dense_weight,
    )
    documents = retriever.invoke(args.question)
    if args.retrieve_only:
        print(json.dumps([doc.model_dump() for doc in documents], ensure_ascii=False, indent=2))
        return
    result = generate_answer(args.question, documents, settings.chat_model())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(result['answer'])
    for citation in result['citations']:
        print(f"[{citation['source_id']}] {citation['citation_label']} | document ID: {citation['document_id']}")


if __name__ == '__main__':
    main()
