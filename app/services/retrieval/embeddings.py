from __future__ import annotations

from collections import OrderedDict
import contextlib
import hashlib
import io
import logging
import math
import re
from pathlib import Path


ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def tokenize_text(text: str) -> list[str]:
    lowered = text.lower()
    tokens = [token.lower() for token in ASCII_TOKEN_PATTERN.findall(lowered)]
    chars = CJK_CHAR_PATTERN.findall(text)
    tokens.extend(chars)
    tokens.extend("".join(chars[index : index + 2]) for index in range(len(chars) - 1))
    return tokens


class EmbeddingService:
    def __init__(self, *, model_name: str = "", device: str = "cpu", fallback_dimensions: int = 48) -> None:
        self.model_name = model_name.strip()
        self.device = device
        self.fallback_dimensions = fallback_dimensions
        self.dimensions = fallback_dimensions
        self._model = None
        self._load_error = ""
        self._using_sentence_transformer = False
        self.cache_max_entries = 256
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

    def embed_text(self, text: str) -> list[float]:
        cache_key = self._build_cache_key(text)
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            self._embedding_cache.move_to_end(cache_key)
            self._cache_hits += 1
            return list(cached)
        self._cache_misses += 1

        model = self._load_model()
        if model is not None:
            vector = model.encode(
                [text or ""],
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )[0]
            values = [float(item) for item in vector.tolist()]
            self.dimensions = len(values)
            self._store_cache(cache_key, values)
            return values

        vector = [0.0] * self.fallback_dimensions
        tokens = tokenize_text(text)
        if not tokens:
            self._store_cache(cache_key, vector)
            return vector

        for token in tokens:
            index = hash(token) % self.fallback_dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            self._store_cache(cache_key, vector)
            return vector
        normalized = [value / norm for value in vector]
        self._store_cache(cache_key, normalized)
        return normalized

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not self.model_name:
            return None

        model_path = Path(self.model_name)
        if model_path.is_absolute() and not model_path.exists():
            self._load_error = f"embedding model path not found: {self.model_name}"
            return None

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            from transformers.utils import logging as hf_logging  # type: ignore

            hf_logging.set_verbosity_error()
            logging.getLogger("transformers.utils.loading_report").setLevel(logging.ERROR)

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self._model = SentenceTransformer(self.model_name, device=self.device)
            get_dimension = getattr(self._model, "get_embedding_dimension", None) or getattr(
                self._model,
                "get_sentence_embedding_dimension",
            )
            self.dimensions = int(get_dimension() or self.fallback_dimensions)
            self._using_sentence_transformer = True
            return self._model
        except Exception as exc:  # pragma: no cover - fallback path
            self._load_error = str(exc)
            self._model = None
            self._using_sentence_transformer = False
            return None

    @property
    def using_sentence_transformer(self) -> bool:
        return self._using_sentence_transformer

    @property
    def load_error(self) -> str:
        return self._load_error

    def cache_stats(self) -> dict[str, int]:
        return {
            "size": len(self._embedding_cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
        }

    def _build_cache_key(self, text: str) -> str:
        raw = f"{self.model_name}|{self.device}|{text or ''}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _store_cache(self, cache_key: str, values: list[float]) -> None:
        self._embedding_cache[cache_key] = list(values)
        self._embedding_cache.move_to_end(cache_key)
        while len(self._embedding_cache) > self.cache_max_entries:
            self._embedding_cache.popitem(last=False)

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        return sum(x * y for x, y in zip(a, b))
