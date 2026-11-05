import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pinecone.db_data.dataclasses.fetch_response import FetchResponse
from pinecone.db_data.dataclasses.vector import Vector
from pinecone.core.openapi.db_data.model.query_response import QueryResponse
from pinecone.core.openapi.db_data.model.scored_vector import ScoredVector

from lease_rag.chunking import chunk_pdf
from lease_rag.config import ROOT, Settings
from lease_rag.manifest import read_manifest
from lease_rag.retrieval import TenantHybridRetriever, authorized_scope, generate_answer, load_snapshot
from lease_rag.storage import encode_sparse, ingest_documents, pinecone_metadata, verify_records


def document(chunk_id='alice-pets', tenant='alice', doc_id='alice-lease', access='tenant'):
    return Document(page_content='11. PETS. A $200 pet deposit is required.', metadata={
        'chunk_id': chunk_id, 'document_id': doc_id, 'tenant_name': tenant, 'access': access,
        'source_filename': 'lease.pdf', 'document_type': 'lease', 'document_status': 'signed',
        'page_numbers': [2], 'section_id': '11', 'clause_id': None,
        'source_spans': [{'page_number': 2, 'char_start': 0, 'char_end': 8, 'text': '11. PETS'}],
        'citation_label': 'lease.pdf, PDF p. 2, 11',
    })


def match(doc):
    return {'id': doc.metadata['chunk_id'], 'metadata': pinecone_metadata(doc), 'score': 0.9}


def filter_matches(metadata, expression):
    if '$and' in expression:
        return all(filter_matches(metadata, term) for term in expression['$and'])
    if '$or' in expression:
        return any(filter_matches(metadata, term) for term in expression['$or'])
    for key, condition in expression.items():
        if '$eq' in condition and metadata.get(key) != condition['$eq']:
            return False
        if '$in' in condition and metadata.get(key) not in condition['$in']:
            return False
    return True


class FakeIndex:
    def __init__(self):
        self.records = {}
        self.calls = []

    def upsert(self, *, namespace, vectors):
        self.records.setdefault(namespace, {}).update({v['id']: v for v in vectors})

    def fetch(self, *, ids, namespace):
        return FetchResponse(namespace=namespace, usage={}, vectors={
            key: Vector.from_dict({'values': [], **self.records[namespace][key]})
            for key in ids if key in self.records.get(namespace, {})})

    def query(self, **kwargs):
        self.calls.append(kwargs)
        records = list(self.records.get(kwargs['namespace'], {}).values())
        matches = [ScoredVector(id=record['id'], metadata=record['metadata'], score=0.9)
                   for record in records if filter_matches(record['metadata'], kwargs['filter'])]
        return QueryResponse(matches=matches[:kwargs['top_k']], namespace=kwargs['namespace'])


class LocalRagTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = Settings({'PINECONE_INDEX_NAME': 'test-dense'}, root=self.root)
        self.documents = [document(), document('bob-pets', 'bob', 'bob-lease'),
                          document('law', '', 'nc-law', 'shared')]
        self.snapshot = {
            'schema_version': 1, 'profile': self.settings.profile, 'namespace': 'test',
            'dense_index': 'test-dense', 'sparse_index': 'test-dense-sparse',
            'documents': {d.metadata['document_id']: {key: d.metadata[key] for key in ('access', 'tenant_name')}
                          for d in self.documents},
        }
        self.pc = SimpleNamespace(inference=SimpleNamespace(embed=Mock(side_effect=lambda **kw: [
            {'sparse_indices': [1, 2], 'sparse_values': [0.5, 0.7]} for _ in kw['inputs']])))
        self.embeddings = SimpleNamespace(embed_query=Mock(return_value=[1.0, 0.0]),
                                          embed_documents=Mock(side_effect=lambda texts: [[1.0, 0.0]] * len(texts)))

    def retriever(self, dense=None, sparse=None, **kwargs):
        return TenantHybridRetriever(
            dense_index=dense or Mock(query=Mock(return_value={'matches': [match(self.documents[0])]})),
            sparse_index=sparse or Mock(query=Mock(return_value={'matches': [match(self.documents[2])]})),
            embeddings=self.embeddings, pc=self.pc, snapshot=self.snapshot, tenant_name=' Alice ', **kwargs)

    def test_local_env_ignores_shell_keys_and_colab(self):
        path = self.root / '.env'
        path.write_text('PINECONE_API_KEY=file-secret\nNEBIUS_API_KEY=embedding-secret\n')
        with patch.dict('os.environ', {'PINECONE_API_KEY': 'stale-secret'}), \
                patch('builtins.input', side_effect=AssertionError('No prompts')):
            settings = Settings.load(path)
            self.assertEqual(settings.require('PINECONE_API_KEY'), 'file-secret')
            self.assertNotIn('file-secret', repr(settings))
            with self.assertRaisesRegex(ValueError, 'PINECONE_INDEX_NAME'):
                settings.dense_index_name

    def test_both_searches_are_filtered_and_hybrid_merges_deduplicates(self):
        a, _, law = self.documents
        dense = Mock(query=Mock(return_value={'matches': [match(a), match(law)]}))
        sparse = Mock(query=Mock(return_value={'matches': [match(law)]}))
        result = self.retriever(dense, sparse, k=2).invoke('What about Bob and my pet deposit?')
        self.assertEqual([d.metadata['chunk_id'] for d in result], ['law', 'alice-pets'])
        dense_filter = dense.query.call_args.kwargs['filter']
        self.assertEqual(dense_filter, sparse.query.call_args.kwargs['filter'])
        self.assertTrue(filter_matches(a.metadata, dense_filter))
        self.assertTrue(filter_matches(law.metadata, dense_filter))
        self.assertFalse(filter_matches(self.documents[1].metadata, dense_filter))
        self.assertIn('vector', dense.query.call_args.kwargs)
        self.assertIn('sparse_vector', sparse.query.call_args.kwargs)
        self.assertEqual(result[0].metadata['search_ranks'], {'dense': 2, 'sparse': 1})

    def test_unknown_tenant_and_foreign_document_fail_before_embedding(self):
        for tenant, selected in [('mallory', None), ('alice', ['bob-lease'])]:
            with self.assertRaises(PermissionError):
                authorized_scope(self.snapshot, tenant, selected)
        retriever = self.retriever(document_ids=['bob-lease'])
        with self.assertRaises(PermissionError):
            retriever.invoke('pets')
        self.embeddings.embed_query.assert_not_called()

    def test_out_of_scope_or_corrupt_hits_never_reach_generation(self):
        dense = Mock(query=Mock(return_value={'matches': [match(self.documents[1])]}))
        with self.assertRaises(PermissionError):
            self.retriever(dense).invoke('pets')
        corrupt = match(self.documents[0])
        corrupt['metadata']['tenant_name'] = 'bob'
        dense.query.return_value = {'matches': [corrupt]}
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.retriever(dense).invoke('pets')

    def test_shared_document_visible_to_each_tenant(self):
        for tenant in ['ALICE', 'bob']:
            _, _, shared, scope = authorized_scope(self.snapshot, tenant)
            self.assertEqual(shared, {'nc-law'})
            self.assertTrue(filter_matches(self.documents[2].metadata, scope))

    def test_sparse_failures_and_invalid_results_do_not_fall_back_silently(self):
        self.pc.inference.embed.side_effect = RuntimeError('provider unavailable')
        with self.assertRaises(RuntimeError):
            self.retriever().invoke('pets')
        self.pc.inference.embed.side_effect = None
        for result in [[], [{'sparse_indices': [1, 1], 'sparse_values': [1, 2]}],
                       [{'sparse_indices': [1], 'sparse_values': [float('nan')]}]]:
            self.pc.inference.embed.return_value = result
            with self.assertRaises(ValueError):
                encode_sparse(self.pc, ['pets'], role='query', profile=self.settings.profile)

    def test_answer_chain_receives_only_evidence_and_resolves_citations(self):
        captured = []
        def respond(prompt):
            captured.append(prompt.to_string())
            return AIMessage(content=json.dumps({'answer': 'The deposit is $200 [S1].', 'citations': ['S1']}))
        result = generate_answer('Pet deposit?', [self.documents[0]], RunnableLambda(respond))
        self.assertEqual(result['citations'][0]['document_id'], 'alice-lease')
        self.assertEqual(result['citations'][0]['page_numbers'], [2])
        self.assertNotIn('bob-lease', captured[0])
        self.assertIn('Do not infer', captured[0])
        self.assertIn('source_spans', captured[0])
        for output in [{'answer': 'Unknown [S99]', 'citations': ['S99']},
                       {'answer': 'No reference', 'citations': ['S1']},
                       {'answer': 'Invented fee', 'citations': []}]:
            with self.assertRaises(ValueError):
                generate_answer('pets', [self.documents[0]],
                                RunnableLambda(lambda _, value=output: AIMessage(content=json.dumps(value))))
        unused = Mock()
        self.assertEqual(generate_answer('pets', [], unused)['citations'], [])
        unused.assert_not_called()

    def test_ingestion_query_roundtrip_and_failed_snapshot_publication(self):
        dense, sparse = FakeIndex(), FakeIndex()
        active = self.root / 'active.json'
        indexes = lambda pc, name, **kw: sparse if kw['sparse'] else dense
        with patch('lease_rag.storage.prepare_index', side_effect=indexes), redirect_stdout(io.StringIO()):
            state = ingest_documents(self.documents, self.settings, active_path=active,
                                     clients=(self.pc, self.embeddings))
            retriever = self.retriever(dense, sparse)
            retriever.snapshot = state
            hits = retriever.invoke('pet deposit')
            self.assertEqual({d.metadata['document_id'] for d in hits}, {'alice-lease', 'nc-law'})
            before = active.read_text()
            again = ingest_documents(self.documents, self.settings, active_path=active,
                                     clients=(self.pc, self.embeddings))
            self.assertEqual(state['namespace'], again['namespace'])
            self.assertEqual(len(dense.records[state['namespace']]), 3)
            changed = copy.deepcopy(self.documents)
            changed[0].metadata['tenant_name'] = 'charlie'
            with patch('lease_rag.storage.verify_records', side_effect=[None, RuntimeError('sparse incomplete')]):
                with self.assertRaises(RuntimeError):
                    ingest_documents(changed, self.settings, active_path=active,
                                     clients=(self.pc, self.embeddings))
            self.assertEqual(active.read_text(), before)
            self.assertEqual(len(dense.records), 2)  # New ownership gets a different snapshot.
            self.assertEqual(load_snapshot(self.settings, active)['namespace'], state['namespace'])

    def test_fetch_sdk_response_retries_missing_ids_and_fails_if_incomplete(self):
        index = Mock()
        index.fetch.side_effect = [
            FetchResponse(namespace='test', vectors={'a': Vector(id='a', values=[1.0])}, usage={}),
            FetchResponse(namespace='test', vectors={'b': Vector(id='b', values=[1.0])}, usage={}),
        ]
        with patch('lease_rag.storage.time.sleep'):
            verify_records(index, ['a', 'b'], 'test', attempts=2)
        self.assertEqual(index.fetch.call_args_list[1].kwargs['ids'], ['b'])
        index.fetch.side_effect = None
        index.fetch.return_value = FetchResponse(namespace='test', vectors={}, usage={})
        with patch('lease_rag.storage.time.sleep'), self.assertRaisesRegex(RuntimeError, 'not visible'):
            verify_records(index, ['missing'], 'test', attempts=1)

    def test_manifest_rejects_unassigned_shared_private_and_path_traversal(self):
        (self.root / 'lease.pdf').write_bytes(b'%PDF-test')
        path = self.root / 'manifest.json'
        item = dict(path='lease.pdf', document_id='lease1', tenant_name='Alice')
        path.write_text(json.dumps({'documents': [item]}))
        self.assertEqual(read_manifest(path, self.root)[0]['tenant_name'], 'alice')
        for bad in [dict(item, access='shared'), dict(item, path='../outside.pdf'),
                    dict(item, tenant_name=''), dict(item, document_id='')]:
            path.write_text(json.dumps({'documents': [bad]}))
            with self.assertRaises(ValueError):
                read_manifest(path, self.root)
        path.write_text(json.dumps({'documents': [item]}))
        (self.root / 'unassigned.pdf').write_bytes(b'%PDF-test')
        with self.assertRaisesRegex(ValueError, 'Unassigned'):
            read_manifest(path, self.root)

    def test_real_pdfs_preserve_citations_blank_pet_fields_and_unique_ownership(self):
        records = read_manifest(ROOT / 'documents.example.json', ROOT / 'data')
        lease_chunks = None
        for record in records:
            chunks, report = chunk_pdf(record['pdf_path'], record, ROOT / 'data')
            self.assertGreater(len(chunks), 10)
            for chunk in chunks:
                meta = chunk.metadata
                self.assertEqual(meta['document_id'], record['document_id'])
                self.assertEqual(meta['tenant_name'], record['tenant_name'])
                self.assertTrue(meta['source_spans'])
                for span in meta['source_spans']:
                    self.assertGreaterEqual(span['page_number'], 1)
                    self.assertLessEqual(span['page_number'], report['page_count'])
                    self.assertEqual(len(span['text']), span['char_end'] - span['char_start'])
                pinecone_metadata(chunk)
            if record['access'] == 'tenant':
                lease_chunks = chunks
                pet = next(d for d in chunks if d.metadata['section_id'] == '11')
                self.assertEqual(pet.metadata['page_numbers'], [2, 3])
                self.assertFalse(pet.metadata['has_unfilled_fields'])
                other = dict(record, tenant_name='another tenant', document_id='another-lease')
                others, _ = chunk_pdf(record['pdf_path'], other, ROOT / 'data')
                self.assertFalse({d.metadata['chunk_id'] for d in chunks}
                                 & {d.metadata['chunk_id'] for d in others})
        self.assertIsNotNone(lease_chunks)


if __name__ == '__main__':
    unittest.main()
