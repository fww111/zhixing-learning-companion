from __future__ import annotations

import hashlib
import importlib.machinery
import math
import os
import re
import sys
import types
from functools import lru_cache
from pathlib import PurePosixPath, Path
from typing import Any

from app.core.config import settings


EMBEDDING_DIMENSIONS = 64


class ChromaVectorService:
    def __init__(self, client: Any | None = None):
        self.client = client if client is not None else self._create_client()

    def _create_client(self) -> Any:
        import chromadb
        from chromadb.config import Settings

        return chromadb.PersistentClient(
            path=settings.chroma_persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

    def collection_name(self, course_id: int) -> str:
        provider = self._collection_segment(getattr(settings, "embedding_provider", "hash"))
        raw_model = str(getattr(settings, "embedding_model", "hash"))
        model = self._collection_segment(raw_model)
        name = f"course_{course_id}_{provider}_{model}"
        if len(name) <= 63:
            return name

        normalized_model = raw_model.replace("\\", "/")
        model_tail = self._collection_segment(PurePosixPath(normalized_model).name or model)
        digest = hashlib.blake2s(raw_model.encode("utf-8"), digest_size=4).hexdigest()
        prefix = f"course_{course_id}_{provider}_"
        suffix = f"_{digest}"
        available_model_chars = max(1, 63 - len(prefix) - len(suffix))
        return f"{prefix}{model_tail[:available_model_chars].strip('_-') or 'model'}{suffix}"

    def collection(self, course_id: int) -> Any:
        return self.client.get_or_create_collection(
            name=self.collection_name(course_id),
            embedding_function=None,
        )

    def upsert_chunks(self, course_id: int, chunks: list[dict[str, Any]], *, skip_existing: bool = False) -> None:
        if not chunks:
            return

        collection = self.collection(course_id)
        batch_size = max(1, int(getattr(settings, "embedding_batch_size", 16)))
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            if skip_existing:
                batch = self._filter_missing_chunks(collection, batch)
                if not batch:
                    continue
            collection.upsert(
                ids=[f"chunk-{chunk['id']}" for chunk in batch],
                embeddings=self.embed_texts([chunk["content"] for chunk in batch]),
                documents=[chunk["content"] for chunk in batch],
                metadatas=[
                    {
                        "chunk_id": chunk["id"],
                        "course_id": course_id,
                        "source_locator": chunk.get("source_locator") or "",
                    }
                    for chunk in batch
                ],
            )

    def delete_chunks(self, course_id: int, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return

        self.collection(course_id).delete(ids=[f"chunk-{chunk_id}" for chunk_id in chunk_ids])

    def search(self, course_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
        raw_results = self.collection(course_id).query(
            query_embeddings=[self.embed_text(query)],
            n_results=limit,
        )
        ids = raw_results.get("ids", [[]])[0]
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        results = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata or {}
            results.append(
                {
                    "id": chunk_id,
                    "chunk_id": metadata.get("chunk_id"),
                    "course_id": metadata.get("course_id"),
                    "source_locator": metadata.get("source_locator"),
                    "content": documents[index] if index < len(documents) else None,
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return results

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized_texts = [self._embedding_input(text) for text in texts]
        provider = getattr(settings, "embedding_provider", "hash").lower().strip()
        if provider in {"local_bge", "bge", "sentence_transformers"}:
            return self._embed_texts_with_sentence_transformer(normalized_texts)
        return [self._embed_text_with_hash(text) for text in normalized_texts]

    def _embed_texts_with_sentence_transformer(self, texts: list[str]) -> list[list[float]]:
        model_name = getattr(settings, "embedding_model", "BAAI/bge-m3")
        device = getattr(settings, "embedding_device", "cpu")
        cache_folder = getattr(settings, "embedding_cache_dir", "data/models/embeddings")
        max_seq_length = int(getattr(settings, "embedding_max_seq_length", 512))
        model = _get_bge_transformers_encoder(
            model_name,
            device,
            cache_folder,
            max_seq_length,
        )
        if model is not None:
            return model.encode(
                texts,
                batch_size=max(1, int(getattr(settings, "embedding_batch_size", 16))),
            )

        model = _get_sentence_transformer(
            model_name,
            device,
            cache_folder,
            max_seq_length,
        )
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=max(1, int(getattr(settings, "embedding_batch_size", 16))),
        )
        return [[float(value) for value in embedding] for embedding in embeddings]

    def _embed_text_with_hash(self, text: str) -> list[float]:
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            tokens = [char for char in text.lower() if not char.isspace()]

        vector = [0.0] * EMBEDDING_DIMENSIONS
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def _collection_segment(self, value: str) -> str:
        segment = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
        return segment or "default"

    def _embedding_input(self, text: str) -> str:
        max_chars = int(getattr(settings, "embedding_max_chars", 512))
        value = text or ""
        if max_chars <= 0 or len(value) <= max_chars:
            return value
        return value[:max_chars]

    def _filter_missing_chunks(self, collection: Any, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [f"chunk-{chunk['id']}" for chunk in chunks]
        try:
            existing = collection.get(ids=ids, include=[])
        except Exception:
            return chunks
        existing_ids = set(existing.get("ids") or [])
        return [chunk for chunk in chunks if f"chunk-{chunk['id']}" not in existing_ids]

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is None:
            return
        close()


class MilvusVectorService(ChromaVectorService):
    def _create_client(self) -> Any:
        kwargs = {
            "uri": getattr(settings, "milvus_uri", "http://127.0.0.1:19530"),
            "token": getattr(settings, "milvus_token", ""),
            "user": getattr(settings, "milvus_user", ""),
            "password": getattr(settings, "milvus_password", ""),
            "db_name": getattr(settings, "milvus_db_name", ""),
        }
        client_kwargs = {key: value for key, value in kwargs.items() if value}
        uri = str(client_kwargs.get("uri", ""))
        local_uri = self._is_milvus_lite_uri(uri)
        original_env_uri = os.environ.get("MILVUS_URI") if local_uri else None
        if local_uri:
            Path(uri).parent.mkdir(parents=True, exist_ok=True)
            os.environ["MILVUS_URI"] = "http://127.0.0.1:19530"
        try:
            from pymilvus import MilvusClient

            return MilvusClient(**client_kwargs)
        finally:
            if local_uri:
                if original_env_uri is None:
                    os.environ.pop("MILVUS_URI", None)
                else:
                    os.environ["MILVUS_URI"] = original_env_uri

    def collection(self, course_id: int) -> str:
        name = self.collection_name(course_id)
        if not self.client.has_collection(name):
            self.client.create_collection(
                collection_name=name,
                dimension=self._vector_dimension(),
                primary_field_name="id",
                id_type="string",
                vector_field_name="vector",
                metric_type="COSINE",
                auto_id=False,
                enable_dynamic_field=True,
            )
        return name

    def upsert_chunks(self, course_id: int, chunks: list[dict[str, Any]], *, skip_existing: bool = False) -> None:
        if not chunks:
            return

        collection_name = self.collection(course_id)
        batch_size = max(1, int(getattr(settings, "embedding_batch_size", 16)))
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            if skip_existing:
                batch = self._filter_missing_milvus_chunks(collection_name, batch)
                if not batch:
                    continue
            embeddings = self.embed_texts([chunk["content"] for chunk in batch])
            self.client.upsert(
                collection_name=collection_name,
                data=[
                    {
                        "id": f"chunk-{chunk['id']}",
                        "vector": embeddings[index],
                        "chunk_id": int(chunk["id"]),
                        "course_id": int(course_id),
                        "source_locator": chunk.get("source_locator") or "",
                        "content": chunk["content"],
                    }
                    for index, chunk in enumerate(batch)
                ],
            )

    def delete_chunks(self, course_id: int, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return
        collection_name = self.collection(course_id)
        self._load_collection(collection_name)
        self.client.delete(
            collection_name=collection_name,
            ids=[f"chunk-{chunk_id}" for chunk_id in chunk_ids],
        )

    def search(self, course_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
        collection_name = self.collection(course_id)
        self._load_collection(collection_name)
        raw_results = self.client.search(
            collection_name=collection_name,
            data=[self.embed_text(query)],
            limit=limit,
            output_fields=["chunk_id", "course_id", "source_locator", "content"],
            search_params={"metric_type": "COSINE"},
        )
        hits = raw_results[0] if raw_results else []
        results = []
        for hit in hits:
            entity = hit.get("entity") or {}
            results.append(
                {
                    "id": hit.get("id"),
                    "chunk_id": entity.get("chunk_id"),
                    "course_id": entity.get("course_id"),
                    "source_locator": entity.get("source_locator"),
                    "content": entity.get("content"),
                    "distance": hit.get("distance"),
                }
            )
        return results

    def _vector_dimension(self) -> int:
        return _embedding_dimension(
            getattr(settings, "embedding_provider", "hash"),
            getattr(settings, "embedding_model", "hash"),
            getattr(settings, "embedding_device", "cpu"),
            getattr(settings, "embedding_cache_dir", "data/models/embeddings"),
            int(getattr(settings, "embedding_max_seq_length", 512)),
        )

    def _filter_missing_milvus_chunks(self, collection_name: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [f"chunk-{chunk['id']}" for chunk in chunks]
        try:
            self._load_collection(collection_name)
            existing = self.client.get(collection_name=collection_name, ids=ids, output_fields=["id"])
        except Exception:
            return chunks
        existing_ids = {row.get("id") for row in existing}
        return [chunk for chunk in chunks if f"chunk-{chunk['id']}" not in existing_ids]

    def _load_collection(self, collection_name: str) -> None:
        load_collection = getattr(self.client, "load_collection", None)
        if load_collection is None:
            return
        load_collection(collection_name)

    def _is_milvus_lite_uri(self, uri: str) -> bool:
        normalized = (uri or "").strip().lower()
        if not normalized:
            return False
        if normalized.startswith(("http://", "https://", "tcp://", "grpc://")):
            return False
        return normalized.endswith(".db")


@lru_cache(maxsize=4)
def _get_sentence_transformer(model_name: str, device: str, cache_folder: str, max_seq_length: int) -> Any:
    Path(cache_folder).mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = cache_folder
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = cache_folder
    _install_torchcodec_text_embedding_stub_if_needed()

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device, cache_folder=cache_folder)
    if max_seq_length > 0:
        model.max_seq_length = max_seq_length
    return model


@lru_cache(maxsize=4)
def _get_bge_transformers_encoder(model_name: str, device: str, cache_folder: str, max_seq_length: int) -> Any | None:
    try:
        return _BgeM3TransformersEncoder(model_name, device, cache_folder, max_seq_length)
    except Exception:
        return None


class _BgeM3TransformersEncoder:
    def __init__(self, model_name: str, device: str, cache_folder: str, max_seq_length: int) -> None:
        Path(cache_folder).mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = cache_folder
        os.environ["TRANSFORMERS_CACHE"] = cache_folder
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = cache_folder

        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.device = device
        self.max_seq_length = max_seq_length if max_seq_length > 0 else 512
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_folder,
            local_files_only=Path(model_name).exists(),
        )
        self.model = AutoModel.from_pretrained(
            model_name,
            cache_dir=cache_folder,
            local_files_only=Path(model_name).exists(),
        )
        self.model.to(device)
        self.model.eval()

    def encode(self, texts: list[str], batch_size: int) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), max(1, batch_size)):
            batch_texts = texts[start : start + max(1, batch_size)]
            inputs = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=self.max_seq_length,
                return_tensors="pt",
            )
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with self.torch.no_grad():
                output = self.model(**inputs)
            pooled = self._mean_pool(output.last_hidden_state, inputs["attention_mask"])
            pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
            embeddings.extend([[float(value) for value in row] for row in pooled.cpu().tolist()])
        return embeddings

    def dimension(self) -> int:
        hidden_size = getattr(getattr(self.model, "config", None), "hidden_size", None)
        if hidden_size:
            return int(hidden_size)
        return len(self.encode(["dimension probe"], batch_size=1)[0])

    def _mean_pool(self, token_embeddings: Any, attention_mask: Any) -> Any:
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return (token_embeddings * input_mask_expanded).sum(1) / input_mask_expanded.sum(1).clamp(min=1e-9)


def _install_torchcodec_text_embedding_stub_if_needed() -> None:
    if "torchcodec.decoders" in sys.modules:
        return
    try:
        import torchcodec.decoders  # noqa: F401
        return
    except Exception:
        decoders = types.ModuleType("torchcodec.decoders")
        decoders.__spec__ = importlib.machinery.ModuleSpec("torchcodec.decoders", loader=None)
        decoders.AudioDecoder = None
        decoders.VideoDecoder = None
        torchcodec = sys.modules.get("torchcodec") or types.ModuleType("torchcodec")
        torchcodec.__path__ = []
        torchcodec.__spec__ = importlib.machinery.ModuleSpec("torchcodec", loader=None, is_package=True)
        torchcodec.decoders = decoders
        sys.modules["torchcodec"] = torchcodec
        sys.modules["torchcodec.decoders"] = decoders


@lru_cache(maxsize=8)
def _embedding_dimension(
    provider: str,
    model_name: str,
    device: str,
    cache_folder: str,
    max_seq_length: int,
) -> int:
    normalized_provider = (provider or "hash").lower().strip()
    if normalized_provider not in {"local_bge", "bge", "sentence_transformers"}:
        return EMBEDDING_DIMENSIONS
    encoder = _get_bge_transformers_encoder(model_name, device, cache_folder, max_seq_length)
    if encoder is not None:
        return int(encoder.dimension())
    model = _get_sentence_transformer(model_name, device, cache_folder, max_seq_length)
    dimension = getattr(model, "get_sentence_embedding_dimension", lambda: None)()
    if dimension:
        return int(dimension)
    embedding = model.encode(["dimension probe"], normalize_embeddings=True, batch_size=1)[0]
    return len(embedding)
