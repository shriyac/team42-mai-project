"""Pinecone dense/sparse storage and an atomic active-snapshot pointer."""
from pathlib import Path
from tempfile import NamedTemporaryFile
from collections.abc import Mapping
import json
import math
import time

from langchain_core.documents import Document
from pinecone import ServerlessSpec

from .config import ROOT, fingerprint

ACTIVE_PATH = ROOT / 'artifacts/lease_rag_local/active.json'


def response_field(response, name):
    """Read SDK response attributes, also accepting mapping-based responses."""
    return response[name] if isinstance(response, Mapping) else getattr(response, name)


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
    temporary.replace(path)


def prepare_index(pc, name, *, sparse, settings):
    if not pc.has_index(name):
        args = dict(name=name, metric='dotproduct' if sparse else 'cosine',
                    vector_type='sparse' if sparse else 'dense',
                    spec=ServerlessSpec(cloud=settings.get('PINECONE_CLOUD', 'aws'),
                                        region=settings.get('PINECONE_REGION', 'us-east-1')))
        if not sparse:
            args['dimension'] = settings.profile['dimensions']
        pc.create_index(**args)
    for _ in range(60):
        description = pc.describe_index(name)
        if description.metric != ('dotproduct' if sparse else 'cosine'):
            raise ValueError(f'{name}: incompatible metric; choose a different index name in .env.')
        if description.vector_type != ('sparse' if sparse else 'dense'):
            raise ValueError(f'{name}: incompatible vector type.')
        if not sparse and description.dimension != settings.profile['dimensions']:
            raise ValueError(f'{name}: incompatible embedding dimension.')
        if description.status['ready']:
            return pc.Index(host=description.host)
        time.sleep(2)
    raise TimeoutError(f'Index {name} did not become ready.')


def encode_sparse(pc, texts, *, role, profile):
    response = pc.inference.embed(
        model=profile['sparse_model'], inputs=texts,
        parameters={'input_type': role, 'max_tokens_per_sequence': profile['sparse_max_tokens'],
                    'truncate': 'NONE'},
    )
    items = list(response)
    if len(items) != len(texts):
        raise ValueError('Sparse encoder returned the wrong number of vectors.')
    vectors = []
    for item in items:
        indices, values = list(item['sparse_indices']), list(item['sparse_values'])
        if (not indices or len(indices) != len(values) or len(set(indices)) != len(indices)
                or any(not isinstance(i, int) or not 0 <= i < 2**32 for i in indices)
                or not all(math.isfinite(v) for v in values)):
            raise ValueError('Invalid or empty sparse embedding.')
        vectors.append({'indices': indices, 'values': values})
    return vectors


def pinecone_metadata(doc):
    meta = doc.metadata
    flat = {key: meta[key] for key in ('chunk_id', 'document_id', 'tenant_name', 'access',
                                      'source_filename', 'document_type', 'document_status')}
    flat.update(text=doc.page_content, evidence_json=json.dumps(meta, ensure_ascii=False))
    # Preserve full page/clause evidence while staying below Pinecone's 40KB limit.
    if len(json.dumps(flat, ensure_ascii=False).encode()) > 38_000:
        raise ValueError(f"Chunk {meta['chunk_id']} exceeds the metadata budget; reduce chunk size.")
    return flat


def restore_document(match):
    meta = response_field(match, 'metadata')
    evidence = json.loads(meta['evidence_json'])
    for key in ('chunk_id', 'document_id', 'tenant_name', 'access'):
        if evidence.get(key) != meta.get(key):
            raise ValueError('Stored citation identity does not match filterable metadata.')
    if response_field(match, 'id') != evidence['chunk_id']:
        raise ValueError('Stored vector identity does not match chunk identity.')
    return Document(page_content=meta['text'], metadata=evidence)


def verify_records(index, ids, namespace, attempts=15):
    missing = set(ids)
    for _ in range(attempts):
        remaining = sorted(missing)
        for start in range(0, len(remaining), 100):
            response = index.fetch(ids=remaining[start:start + 100], namespace=namespace)
            missing.difference_update(response_field(response, 'vectors'))
        if not missing:
            return
        time.sleep(2)
    raise RuntimeError(f'{len(missing)} records are not visible; active snapshot has not been changed.')


def ingest_documents(documents, settings, *, active_path=ACTIVE_PATH, clients=None):
    if not documents:
        raise ValueError('No chunks to ingest.')
    metadata = [pinecone_metadata(doc) for doc in documents]
    ids = [doc.metadata['chunk_id'] for doc in documents]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate chunk IDs.')
    profile = settings.profile
    corpus_hash = fingerprint({'profile': profile, 'documents': sorted(zip(ids, metadata))})
    namespace = 'leases-v1-' + corpus_hash[:24]
    if settings.dense_index_name == settings.sparse_index_name:
        raise ValueError('Dense and sparse indexes must have different names.')
    pc, embeddings = clients or settings.clients()
    dense = prepare_index(pc, settings.dense_index_name, sparse=False, settings=settings)
    sparse = prepare_index(pc, settings.sparse_index_name, sparse=True, settings=settings)
    for start in range(0, len(documents), 16):
        batch = documents[start:start + 16]
        texts = [doc.page_content for doc in batch]
        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = encode_sparse(pc, texts, role='passage', profile=profile)
        if len(dense_vectors) != len(batch):
            raise ValueError('Dense encoder returned the wrong number of vectors.')
        dense.upsert(namespace=namespace, vectors=[
            {'id': ids[start + i], 'values': vector, 'metadata': metadata[start + i]}
            for i, vector in enumerate(dense_vectors)])
        sparse.upsert(namespace=namespace, vectors=[
            {'id': ids[start + i], 'sparse_values': vector, 'metadata': metadata[start + i]}
            for i, vector in enumerate(sparse_vectors)])
        print(f'Uploaded {min(start + 16, len(documents))}/{len(documents)} chunks to both indexes.')
    verify_records(dense, ids, namespace)
    verify_records(sparse, ids, namespace)
    registry = {doc.metadata['document_id']: {
        'tenant_name': doc.metadata['tenant_name'], 'access': doc.metadata['access']}
        for doc in documents}
    snapshot = dict(schema_version=1, namespace=namespace, profile=profile,
                    dense_index=settings.dense_index_name, sparse_index=settings.sparse_index_name,
                    documents=registry, chunk_count=len(ids))
    atomic_json(active_path, snapshot)
    return snapshot
