from __future__ import annotations

import importlib.util
import sys
import types

import pytest

from app.core.config import Settings
from app.services import vector_service
from app.services.course_service import CourseService
from app.services.vector_service import ChromaVectorService, MilvusVectorService


class FakeCollection:
    def __init__(self):
        self.upserts = []
        self.queries = []
        self.deletes = []
        self.existing_ids = []

    def upsert(self, ids, documents, metadatas, embeddings=None):
        self.upserts.append(
            {"ids": ids, "documents": documents, "metadatas": metadatas, "embeddings": embeddings}
        )

    def query(self, query_texts=None, query_embeddings=None, n_results=10):
        self.queries.append(
            {"query_texts": query_texts, "query_embeddings": query_embeddings, "n_results": n_results}
        )
        return {
            "ids": [["chunk-1"]],
            "documents": [["梯度下降用于优化损失函数"]],
            "metadatas": [[{"chunk_id": 1, "course_id": 2, "source_locator": "page 3"}]],
            "distances": [[0.12]],
        }

    def delete(self, ids):
        self.deletes.append(ids)

    def get(self, ids, include=None):  # noqa: ARG002
        return {"ids": [chunk_id for chunk_id in ids if chunk_id in self.existing_ids]}


class FakeClient:
    def __init__(self):
        self.collection = FakeCollection()
        self.embedding_function = "unset"

    def get_or_create_collection(self, name, embedding_function="unset"):
        self.name = name
        self.embedding_function = embedding_function
        return self.collection


class FakeMilvusClient:
    def __init__(self):
        self.created = []
        self.closed = False
        self.loads = []
        self.upserts = []
        self.searches = []
        self.deletes = []
        self.collections = set()
        self.rows = {}

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, **kwargs):
        self.created.append(kwargs)
        self.collections.add(kwargs["collection_name"])

    def load_collection(self, collection_name):
        self.loads.append(collection_name)

    def close(self):
        self.closed = True

    def upsert(self, collection_name, data):
        self.upserts.append({"collection_name": collection_name, "data": data})
        self.rows.setdefault(collection_name, {}).update({row["id"]: row for row in data})

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return [
            [
                {
                    "id": "chunk-1",
                    "distance": 0.12,
                    "entity": {"chunk_id": 1, "course_id": 2, "source_locator": "page 3", "content": "梯度下降用于优化损失函数"},
                }
            ]
        ]

    def delete(self, collection_name, ids=None, filter=None):  # noqa: A002
        self.deletes.append({"collection_name": collection_name, "ids": ids, "filter": filter})

    def get(self, collection_name, ids, output_fields=None):  # noqa: ARG002
        rows = self.rows.get(collection_name, {})
        return [rows[row_id] for row_id in ids if row_id in rows]


def force_sentence_transformer_fallback(monkeypatch):
    monkeypatch.setattr(vector_service, "_get_bge_transformers_encoder", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def default_hash_embedding_settings(monkeypatch):
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            chroma_persist_directory="data/chroma",
            embedding_provider="hash",
            embedding_model="hash",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
            embedding_batch_size=16,
            embedding_max_chars=512,
            embedding_max_seq_length=512,
        ),
    )
    original_get_sentence_transformer = getattr(vector_service, "_get_sentence_transformer", None)
    original_get_bge_transformers_encoder = getattr(vector_service, "_get_bge_transformers_encoder", None)
    if hasattr(original_get_sentence_transformer, "cache_clear"):
        vector_service._get_sentence_transformer.cache_clear()
    if hasattr(vector_service, "_embedding_dimension"):
        vector_service._embedding_dimension.cache_clear()
    if hasattr(original_get_bge_transformers_encoder, "cache_clear"):
        vector_service._get_bge_transformers_encoder.cache_clear()
    yield
    if hasattr(original_get_sentence_transformer, "cache_clear"):
        original_get_sentence_transformer.cache_clear()
    if hasattr(vector_service, "_embedding_dimension"):
        vector_service._embedding_dimension.cache_clear()
    if hasattr(original_get_bge_transformers_encoder, "cache_clear"):
        original_get_bge_transformers_encoder.cache_clear()


def test_upsert_chunks_uses_course_scoped_collection():
    client = FakeClient()
    service = ChromaVectorService(client)
    service.upsert_chunks(course_id=2, chunks=[{"id": 1, "content": "梯度下降", "source_locator": "page 3"}])
    assert client.name == "course_2_hash_hash"
    assert client.collection.upserts[0]["ids"] == ["chunk-1"]
    assert client.collection.upserts[0]["metadatas"][0]["chunk_id"] == 1

def test_collection_disables_chroma_default_embedding_function():
    client = FakeClient()
    service = ChromaVectorService(client)

    service.collection(course_id=2)

    assert client.embedding_function is None


def test_upsert_chunks_supplies_local_embeddings():
    client = FakeClient()
    service = ChromaVectorService(client)

    service.upsert_chunks(course_id=2, chunks=[{"id": 1, "content": "gradient descent"}])

    embeddings = client.collection.upserts[0]["embeddings"]
    assert embeddings is not None
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 64


def test_upsert_chunks_batches_local_embeddings(monkeypatch):
    encode_calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            pass

        def encode(self, texts, normalize_embeddings, batch_size=None):
            encode_calls.append(list(texts))
            return [[float(index)] for index, _ in enumerate(texts)]

    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            chroma_persist_directory="data/chroma",
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
            embedding_batch_size=2,
            embedding_max_seq_length=512,
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)
    client = FakeClient()

    ChromaVectorService(client).upsert_chunks(
        course_id=2,
        chunks=[
            {"id": 1, "content": "chunk 1"},
            {"id": 2, "content": "chunk 2"},
            {"id": 3, "content": "chunk 3"},
        ],
    )

    assert encode_calls == [["chunk 1", "chunk 2"], ["chunk 3"]]
    assert [upsert["ids"] for upsert in client.collection.upserts] == [["chunk-1", "chunk-2"], ["chunk-3"]]


def test_upsert_chunks_truncates_embedding_input_without_truncating_documents(monkeypatch):
    encode_calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            pass

        def encode(self, texts, normalize_embeddings, batch_size=None):
            encode_calls.append(list(texts))
            return [[0.1] for _ in texts]

    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            chroma_persist_directory="data/chroma",
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
            embedding_batch_size=16,
            embedding_max_chars=5,
            embedding_max_seq_length=512,
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)
    client = FakeClient()

    ChromaVectorService(client).upsert_chunks(
        course_id=2,
        chunks=[{"id": 1, "content": "1234567890"}],
    )

    assert encode_calls == [["12345"]]
    assert client.collection.upserts[0]["documents"] == ["1234567890"]


def test_upsert_chunks_can_skip_existing_vectors():
    client = FakeClient()
    client.collection.existing_ids = ["chunk-1"]
    service = ChromaVectorService(client)

    service.upsert_chunks(
        course_id=2,
        chunks=[
            {"id": 1, "content": "already indexed"},
            {"id": 2, "content": "new chunk"},
        ],
        skip_existing=True,
    )

    assert client.collection.upserts[0]["ids"] == ["chunk-2"]
    assert client.collection.upserts[0]["documents"] == ["new chunk"]


def test_local_bge_upsert_embeds_chunks_in_one_batch(monkeypatch):
    encode_calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            self.max_seq_length = 8192
            pass

        def encode(self, texts, normalize_embeddings, batch_size=None):
            encode_calls.append({"texts": texts, "normalize_embeddings": normalize_embeddings, "batch_size": batch_size})
            return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
            embedding_max_seq_length=384,
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)
    client = FakeClient()

    ChromaVectorService(client).upsert_chunks(
        course_id=2,
        chunks=[
            {"id": 1, "content": "gradient descent"},
            {"id": 2, "content": "loss function"},
        ],
    )

    assert encode_calls == [
        {"texts": ["gradient descent", "loss function"], "normalize_embeddings": True, "batch_size": 16}
    ]
    assert client.collection.upserts[0]["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert vector_service._get_sentence_transformer("BAAI/bge-m3", "cpu", "data/models/embeddings", 384).max_seq_length == 384


def test_collection_name_includes_embedding_provider_and_model(monkeypatch):
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
        ),
    )
    service = ChromaVectorService(FakeClient())

    assert service.collection_name(2) == "course_2_local_bge_baai_bge_m3"


def test_collection_name_keeps_local_model_path_within_chroma_limit(monkeypatch):
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
        ),
    )
    service = ChromaVectorService(FakeClient())

    name = service.collection_name(6)

    assert len(name) <= 63
    assert name.startswith("course_6_local_bge_")
    assert name[-1].isalnum()


def test_local_bge_provider_uses_sentence_transformer_with_d_drive_cache(monkeypatch):
    class FakeSentenceTransformer:
        instances = []

        def __init__(self, model_name, device, cache_folder):
            self.model_name = model_name
            self.device = device
            self.cache_folder = cache_folder
            FakeSentenceTransformer.instances.append(self)

        def encode(self, texts, normalize_embeddings, batch_size=None):
            assert texts == ["gradient descent"]
            assert normalize_embeddings is True
            assert batch_size == 16
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir="data/models/embeddings",
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)

    service = ChromaVectorService(FakeClient())

    assert service.embed_text("gradient descent") == [0.1, 0.2, 0.3]
    assert FakeSentenceTransformer.instances[0].model_name == "BAAI/bge-m3"
    assert FakeSentenceTransformer.instances[0].device == "cpu"
    assert FakeSentenceTransformer.instances[0].cache_folder == "data/models/embeddings"


def test_local_bge_provider_creates_model_cache_directory(monkeypatch, tmp_path):
    created_cache_folders = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            created_cache_folders.append(cache_folder)

        def encode(self, texts, normalize_embeddings, batch_size=None):  # noqa: ARG002
            return [[0.1, 0.2, 0.3]]

    cache_folder = tmp_path / "models" / "bge-m3"
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir=str(cache_folder),
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)

    ChromaVectorService(FakeClient()).embed_text("gradient descent")

    assert cache_folder.exists()
    assert created_cache_folders == [str(cache_folder)]


def test_local_bge_provider_forces_model_cache_environment_to_d_drive(monkeypatch, tmp_path):
    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            pass

        def encode(self, texts, normalize_embeddings, batch_size=None):  # noqa: ARG002
            return [[0.1, 0.2, 0.3]]

    cache_folder = tmp_path / "d-drive-cache"
    monkeypatch.setenv("HF_HOME", "C:/Users/Administrator/.cache/huggingface")
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", "C:/Users/Administrator/.cache/sentence-transformers")
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir=str(cache_folder),
        ),
    )
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    force_sentence_transformer_fallback(monkeypatch)

    ChromaVectorService(FakeClient()).embed_text("gradient descent")

    assert vector_service.os.environ["HF_HOME"] == str(cache_folder)
    assert vector_service.os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(cache_folder)


def test_local_bge_provider_masks_broken_torchcodec_for_text_embeddings(monkeypatch, tmp_path):
    class FakeSentenceTransformer:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            pass

        def encode(self, texts, normalize_embeddings, batch_size=None):  # noqa: ARG002
            return [[0.1, 0.2, 0.3]]

    class TorchcodecAwareSentenceTransformers(types.ModuleType):
        def __getattr__(self, name):
            if name == "SentenceTransformer":
                torchcodec = sys.modules.get("torchcodec")
                decoders = sys.modules.get("torchcodec.decoders")
                assert torchcodec is not None
                assert torchcodec.__spec__ is not None
                assert decoders is not None
                assert decoders.__spec__ is not None
                assert hasattr(decoders, "AudioDecoder")
                assert hasattr(decoders, "VideoDecoder")
                return FakeSentenceTransformer
            raise AttributeError(name)

    monkeypatch.delitem(sys.modules, "torchcodec", raising=False)
    monkeypatch.delitem(sys.modules, "torchcodec.decoders", raising=False)
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir=str(tmp_path / "models"),
            embedding_batch_size=16,
            embedding_max_chars=512,
            embedding_max_seq_length=512,
        ),
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", TorchcodecAwareSentenceTransformers("sentence_transformers"))
    force_sentence_transformer_fallback(monkeypatch)

    assert ChromaVectorService(FakeClient()).embed_text("gradient descent") == [0.1, 0.2, 0.3]


def test_local_bge_provider_prefers_lightweight_transformers_encoder(monkeypatch, tmp_path):
    encode_calls = []

    class FakeBgeEncoder:
        def __init__(self, model_name, device, cache_folder, max_seq_length):
            self.model_name = model_name
            self.device = device
            self.cache_folder = cache_folder
            self.max_seq_length = max_seq_length

        def encode(self, texts, batch_size):
            encode_calls.append({"texts": texts, "batch_size": batch_size})
            return [[0.1, 0.2, 0.3] for _ in texts]

        def dimension(self):
            return 3

    def fail_sentence_transformer(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("sentence-transformers should not be used for local BGE text embeddings")

    monkeypatch.setattr(vector_service, "_BgeM3TransformersEncoder", FakeBgeEncoder)
    monkeypatch.setattr(vector_service, "_get_sentence_transformer", fail_sentence_transformer)
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir=str(tmp_path / "models"),
            embedding_batch_size=8,
            embedding_max_chars=512,
            embedding_max_seq_length=256,
        ),
    )

    assert ChromaVectorService(FakeClient()).embed_texts(["a", "b"]) == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert encode_calls == [{"texts": ["a", "b"], "batch_size": 8}]


def test_delete_chunks_removes_course_scoped_vector_ids():
    client = FakeClient()
    service = ChromaVectorService(client)

    service.delete_chunks(course_id=2, chunk_ids=[3, 4])

    assert client.name == "course_2_hash_hash"
    assert client.collection.deletes == [["chunk-3", "chunk-4"]]


def test_semantic_search_returns_chunk_metadata():
    service = ChromaVectorService(FakeClient())
    results = service.search(course_id=2, query="优化", limit=3)
    assert results[0]["chunk_id"] == 1
    assert results[0]["source_locator"] == "page 3"


def test_semantic_search_uses_local_query_embedding_not_chroma_default_text_embedding():
    client = FakeClient()
    service = ChromaVectorService(client)

    service.search(course_id=2, query="optimization", limit=3)

    assert client.collection.queries[0]["query_texts"] is None
    assert len(client.collection.queries[0]["query_embeddings"][0]) == 64


class NullMetadataCollection(FakeCollection):
    def query(self, query_texts=None, query_embeddings=None, n_results=10):
        return {
            "ids": [["chunk-legacy"]],
            "documents": [["legacy document"]],
            "metadatas": [[None]],
            "distances": [[0.42]],
        }


class EmptyCollection(FakeCollection):
    def query(self, query_texts=None, query_embeddings=None, n_results=10):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


class SparseCollection(FakeCollection):
    def query(self, query_texts=None, query_embeddings=None, n_results=10):
        return {"ids": [["chunk-sparse"]]}


def test_semantic_search_handles_null_metadata_rows():
    client = FakeClient()
    client.collection = NullMetadataCollection()
    service = ChromaVectorService(client)

    results = service.search(course_id=2, query="legacy", limit=3)

    assert results == [
        {
            "id": "chunk-legacy",
            "chunk_id": None,
            "course_id": None,
            "source_locator": None,
            "content": "legacy document",
            "distance": 0.42,
        }
    ]


def test_semantic_search_handles_empty_results():
    client = FakeClient()
    client.collection = EmptyCollection()
    service = ChromaVectorService(client)

    assert service.search(course_id=2, query="missing", limit=3) == []


def test_semantic_search_handles_sparse_non_empty_results():
    client = FakeClient()
    client.collection = SparseCollection()
    service = ChromaVectorService(client)

    assert service.search(course_id=2, query="sparse", limit=3) == [
        {
            "id": "chunk-sparse",
            "chunk_id": None,
            "course_id": None,
            "source_locator": None,
            "content": None,
            "distance": None,
        }
    ]


def test_course_service_defaults_to_milvus_vector_service():
    assert CourseService.vector_service_cls is MilvusVectorService


def test_milvus_upsert_creates_course_scoped_collection_and_writes_vectors():
    client = FakeMilvusClient()
    service = MilvusVectorService(client)

    service.upsert_chunks(course_id=2, chunks=[{"id": 1, "content": "梯度下降", "source_locator": "page 3"}])

    assert client.created[0]["collection_name"] == "course_2_hash_hash"
    assert client.created[0]["dimension"] == 64
    assert client.upserts[0]["collection_name"] == "course_2_hash_hash"
    assert client.upserts[0]["data"][0]["id"] == "chunk-1"
    assert client.upserts[0]["data"][0]["chunk_id"] == 1
    assert client.upserts[0]["data"][0]["course_id"] == 2
    assert len(client.upserts[0]["data"][0]["vector"]) == 64


def test_milvus_collection_dimension_uses_model_dimension_without_probe_encode(monkeypatch, tmp_path):
    encode_calls = []

    class FakeBgeEncoder:
        def __init__(self, model_name, device, cache_folder):  # noqa: ARG002
            pass

        def dimension(self):
            return 1024

        def encode(self, texts, batch_size):  # noqa: ARG002
            encode_calls.append(list(texts))
            return [[0.1] * 1024 for _ in texts]

    fake_encoder = FakeBgeEncoder("BAAI/bge-m3", "cpu", str(tmp_path / "models"))
    monkeypatch.setattr(vector_service, "_get_bge_transformers_encoder", lambda *args, **kwargs: fake_encoder)
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            embedding_provider="local_bge",
            embedding_model="BAAI/bge-m3",
            embedding_device="cpu",
            embedding_cache_dir=str(tmp_path / "models"),
            embedding_batch_size=16,
            embedding_max_chars=512,
            embedding_max_seq_length=512,
        ),
    )
    client = FakeMilvusClient()

    service = MilvusVectorService(client)
    service.upsert_chunks(course_id=2, chunks=[{"id": 1, "content": "chunk text"}])

    assert client.created[0]["dimension"] == 1024
    assert encode_calls == [["chunk text"]]


def test_milvus_search_returns_chunk_metadata_and_uses_vector_query():
    client = FakeMilvusClient()
    service = MilvusVectorService(client)

    results = service.search(course_id=2, query="优化", limit=3)

    assert client.loads == ["course_2_hash_hash"]
    assert client.searches[0]["collection_name"] == "course_2_hash_hash"
    assert client.searches[0]["limit"] == 3
    assert len(client.searches[0]["data"][0]) == 64
    assert results == [
        {
            "id": "chunk-1",
            "chunk_id": 1,
            "course_id": 2,
            "source_locator": "page 3",
            "content": "梯度下降用于优化损失函数",
            "distance": 0.12,
        }
    ]


def test_milvus_delete_chunks_removes_course_scoped_vector_ids():
    client = FakeMilvusClient()
    service = MilvusVectorService(client)

    service.delete_chunks(course_id=2, chunk_ids=[3, 4])

    assert client.loads == ["course_2_hash_hash"]
    assert client.deletes == [{"collection_name": "course_2_hash_hash", "ids": ["chunk-3", "chunk-4"], "filter": None}]


def test_milvus_skip_existing_loads_collection_before_get():
    client = FakeMilvusClient()
    client.collections.add("course_2_hash_hash")
    client.rows["course_2_hash_hash"] = {"chunk-1": {"id": "chunk-1"}}
    service = MilvusVectorService(client)

    service.upsert_chunks(
        course_id=2,
        chunks=[
            {"id": 1, "content": "already indexed"},
            {"id": 2, "content": "new chunk"},
        ],
        skip_existing=True,
    )

    assert client.loads == ["course_2_hash_hash"]
    assert client.upserts[0]["data"][0]["id"] == "chunk-2"


def test_milvus_vector_service_closes_underlying_client():
    client = FakeMilvusClient()
    service = MilvusVectorService(client)

    service.close()

    assert client.closed is True


def test_milvus_vector_service_initializes_with_configured_client(monkeypatch):
    created = []

    class FakeMilvusClientCtor:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            milvus_uri="http://127.0.0.1:19530",
            milvus_token="token",
            milvus_user="",
            milvus_password="",
            milvus_db_name="softbei",
        ),
    )
    monkeypatch.setitem(sys.modules, "pymilvus", types.SimpleNamespace(MilvusClient=FakeMilvusClientCtor))

    service = MilvusVectorService()

    assert service.client is not None
    assert created == [{"uri": "http://127.0.0.1:19530", "token": "token", "db_name": "softbei"}]


def test_milvus_vector_service_hides_local_lite_uri_from_pymilvus_import(monkeypatch):
    created = []

    class FakeMilvusClientCtor:
        def __init__(self, **kwargs):
            created.append(kwargs)

    class FailingImportPymilvus(types.ModuleType):
        def __getattr__(self, name):
            if name == "MilvusClient":
                assert vector_service.os.environ.get("MILVUS_URI") == "http://127.0.0.1:19530"
                return FakeMilvusClientCtor
            raise AttributeError(name)

    monkeypatch.setenv("MILVUS_URI", "data/milvus/softbei_milvus_lite.db")
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            milvus_uri="data/milvus/softbei_milvus_lite.db",
            milvus_token="",
            milvus_user="",
            milvus_password="",
            milvus_db_name="",
        ),
    )
    monkeypatch.setitem(sys.modules, "pymilvus", FailingImportPymilvus("pymilvus"))

    service = MilvusVectorService()

    assert service.client is not None
    assert created == [{"uri": "data/milvus/softbei_milvus_lite.db"}]
    assert vector_service.os.environ["MILVUS_URI"] == "data/milvus/softbei_milvus_lite.db"


def test_milvus_vector_service_can_import_real_pymilvus_with_local_lite_env_uri(monkeypatch, tmp_path):
    if importlib.util.find_spec("pymilvus") is None:
        pytest.skip("pymilvus is not installed")

    for module_name in [name for name in sys.modules if name == "pymilvus" or name.startswith("pymilvus.")]:
        sys.modules.pop(module_name, None)
    local_uri = str(tmp_path / "milvus_lite.db").replace("\\", "/")
    monkeypatch.setenv("MILVUS_URI", local_uri)
    monkeypatch.setattr(
        vector_service,
        "settings",
        types.SimpleNamespace(
            milvus_uri=local_uri,
            milvus_token="",
            milvus_user="",
            milvus_password="",
            milvus_db_name="",
        ),
    )

    service = MilvusVectorService()
    service.close()

    assert vector_service.os.environ["MILVUS_URI"] == local_uri


def test_settings_load_embedding_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_bge")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cuda")
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", "D:/models/bge")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "8")
    monkeypatch.setenv("EMBEDDING_MAX_CHARS", "256")
    monkeypatch.setenv("EMBEDDING_MAX_SEQ_LENGTH", "384")

    settings = Settings.from_environment()

    assert settings.embedding_provider == "local_bge"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_device == "cuda"
    assert settings.embedding_cache_dir == "D:/models/bge"
    assert settings.embedding_batch_size == 8
    assert settings.embedding_max_chars == 256
    assert settings.embedding_max_seq_length == 384
