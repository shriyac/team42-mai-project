"""LangChain embedding adapter for Nebius and Fireworks Qwen endpoints."""
from pathlib import Path
from hashlib import sha256
import json
import math
from langchain_core.embeddings import Embeddings

class QwenLeaseEmbeddings(Embeddings):
    def __init__(self, client, *, model, dimensions, profile_id, cache_dir,
                 query_instruction, batch_size=16):
        self.client = client
        self.model = model
        self.dimensions = dimensions
        self.profile_id = profile_id
        self.cache_dir = Path(cache_dir) / profile_id
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.query_instruction = query_instruction
        self.batch_size = batch_size

    def validate_vector(self, vector):
        if len(vector) != self.dimensions:
            raise ValueError(f'Expected {self.dimensions} embedding dimensions; received {len(vector)}.')
        values = [float(x) for x in vector]
        if not all(math.isfinite(x) for x in values):
            raise ValueError('Embedding contains non-finite values.')
        norm = math.sqrt(sum(x * x for x in values))
        if norm == 0:
            raise ValueError('Embedding is a zero vector.')
        return [x / norm for x in values]

    def _embed(self, texts, *, role):
        vectors = [None] * len(texts)
        pending = []
        for i, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise ValueError('Embedding inputs must be nonempty strings.')
            key = sha256(json.dumps([role, text], ensure_ascii=False).encode()).hexdigest()
            path = self.cache_dir / f'{key}.json'
            if path.exists():
                cached = json.loads(path.read_text(encoding='utf-8'))
                if cached['profile_id'] != self.profile_id:
                    raise ValueError('Embedding cache configuration mismatch.')
                vectors[i] = self.validate_vector(cached['vector'])
            else:
                pending.append((i, text, path))
        for offset in range(0, len(pending), self.batch_size):
            batch = pending[offset:offset + self.batch_size]
            inputs = [text if role == 'document' else
                      f'Instruct: {self.query_instruction}\nQuery: {text}' for _, text, _ in batch]
            response = self.client.embeddings.create(
                model=self.model, input=inputs, encoding_format='float',
            )
            items = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in items] != list(range(len(batch))):
                raise ValueError('Embedding response has missing, duplicate, or invalid input indices.')
            # Validate the entire batch before persisting any of its vectors.
            normalized = [self.validate_vector(item.embedding) for item in items]
            for (i, _, path), vector in zip(batch, normalized):
                vectors[i] = vector
                temporary = path.with_suffix('.json.tmp')
                temporary.write_text(json.dumps({'profile_id': self.profile_id, 'vector': vector}), encoding='utf-8')
                temporary.replace(path)
        return vectors

    def embed_documents(self, texts):
        return self._embed(texts, role='document')

    def embed_query(self, text):
        return self._embed([text], role='query')[0]