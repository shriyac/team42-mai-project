"""Explicit local .env configuration; no prompts or Colab dependency."""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import json

from dotenv import dotenv_values
from openai import OpenAI
from pinecone import Pinecone

from .embeddings import QwenLeaseEmbeddings

ROOT = Path(__file__).resolve().parents[1]
QUERY_INSTRUCTION = 'Retrieve rental lease clauses including applicable conditions, fees, and exceptions.'
PROVIDERS = {
    'nebius': ('NEBIUS_API_KEY', 'https://api.tokenfactory.nebius.com/v1/', 'Qwen/Qwen3-Embedding-8B'),
    'fireworks': ('FIREWORKS_API_KEY', 'https://api.fireworks.ai/inference/v1/', 'accounts/fireworks/models/qwen3-embedding-8b'),
}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Settings:
    values: dict = field(repr=False)
    root: Path = ROOT

    @classmethod
    def load(cls, env_path=None):
        path = Path(env_path).expanduser().resolve() if env_path else ROOT / '.env'
        if not path.is_file():
            raise FileNotFoundError(f'Missing {path}. Copy .env.example to .env and fill in your keys.')
        return cls(dict(dotenv_values(path, interpolate=False)))

    def get(self, name, default=''):
        return (self.values.get(name) or default).strip()

    def require(self, name):
        value = self.get(name)
        if not value:
            raise ValueError(f'Missing {name} in .env.')
        return value

    @property
    def profile(self):
        provider = self.get('EMBEDDING_PROVIDER', 'nebius').lower()
        if provider not in PROVIDERS:
            raise ValueError('EMBEDDING_PROVIDER must be nebius or fireworks.')
        _, url, model = PROVIDERS[provider]
        return dict(provider=provider, base_url=url, model=model, dimensions=4096,
                    query_instruction=QUERY_INSTRUCTION, adapter_version='qwen-l2-v1',
                    sparse_model='pinecone-sparse-english-v0', sparse_max_tokens=2048)

    @property
    def dense_index_name(self):
        return self.require('PINECONE_INDEX_NAME')

    @property
    def sparse_index_name(self):
        return self.get('PINECONE_SPARSE_INDEX_NAME', self.dense_index_name + '-sparse')

    def clients(self):
        profile = self.profile
        key_name = PROVIDERS[profile['provider']][0]
        embedding_key = self.require(key_name)
        pc = Pinecone(api_key=self.require('PINECONE_API_KEY'))
        embeddings = QwenLeaseEmbeddings(
            OpenAI(api_key=embedding_key, base_url=profile['base_url'], timeout=60, max_retries=2),
            model=profile['model'], dimensions=profile['dimensions'],
            profile_id=fingerprint(profile), cache_dir=self.root / 'artifacts/lease_rag_local/embedding_cache',
            query_instruction=QUERY_INSTRUCTION,
        )
        return pc, embeddings

    def chat_model(self):
        from langchain_openai import ChatOpenAI

        # Generation can use a different provider; the default uses the Nebius key.
        key_name = self.get('LLM_API_KEY_NAME', 'NEBIUS_API_KEY')
        return ChatOpenAI(
            api_key=self.require(key_name),
            base_url=self.get('LLM_BASE_URL', PROVIDERS['nebius'][1]),
            model=self.get('LLM_MODEL', 'Qwen/Qwen3-30B-A3B-Instruct-2507'),
            temperature=0, max_tokens=1500, timeout=60, max_retries=2,
        )
