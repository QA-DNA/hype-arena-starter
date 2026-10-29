"""Frozen discriminative ONNX extraction adapter; no truth classifier or LLM."""

from .batch import BatchExtractor

__all__ = ["BatchExtractor"]
