from __future__ import annotations

import math
import re


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class EmbeddingService:
    def __init__(self, dimensions: int = 48) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
        if not tokens:
            return vector

        for token in tokens:
            index = hash(token) % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        return sum(x * y for x, y in zip(a, b))