from __future__ import annotations

import math
import re


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
    def __init__(self, dimensions: int = 48) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize_text(text)
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
