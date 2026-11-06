"""Run independently: PDF extraction -> LangChain chunks -> embeddings -> Pinecone."""
import argparse
from pathlib import Path

from lease_rag.chunking import chunk_pdf
from lease_rag.config import ROOT, Settings
from lease_rag.manifest import read_manifest
from lease_rag.storage import ACTIVE_PATH, atomic_json, ingest_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'documents.json')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--env', type=Path, help='Local .env path; defaults to .env beside this script.')
    parser.add_argument('--active-file', type=Path, default=ACTIVE_PATH)
    parser.add_argument('--dry-run', action='store_true', help='Extract and validate locally without keys or API calls.')
    args = parser.parse_args()
    records = read_manifest(args.manifest, args.data_dir)
    documents, reports = [], []
    for record in records:
        chunks, report = chunk_pdf(record['pdf_path'], record, args.data_dir.resolve())
        documents.extend(chunks)
        reports.append(report)
        print(f"{report['source_filename']}: {report['page_count']} pages, {len(chunks)} chunks, "
              f"owner={record['tenant_name'] or 'shared'}")
        for warning in report['warnings']:
            print('  Review:', warning)
    # Preflight the entire corpus before creating/updating cloud resources.
    from lease_rag.storage import pinecone_metadata
    for doc in documents:
        pinecone_metadata(doc)
    output_dir = args.active_file.parent
    atomic_json(output_dir / 'prepared_chunks.json', [doc.model_dump() for doc in documents])
    atomic_json(output_dir / 'document_reports.json', reports)
    if args.dry_run:
        print(f'Dry run complete: {len(documents)} chunks. No API calls made.')
        return
    snapshot = ingest_documents(documents, Settings.load(args.env), active_path=args.active_file)
    print(f"Verified {snapshot['chunk_count']} records in each index; active namespace: {snapshot['namespace']}")


if __name__ == '__main__':
    main()
