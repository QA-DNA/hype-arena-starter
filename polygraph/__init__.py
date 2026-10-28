"""Polygraph: tells Hooly's hype from the truth.

No LLM runs here. The pipeline (see docs/ARCHITECTURE.md):
reader -> linker -> attributor -> truth -> judge -> forge -> writer
"""

AS_OF = "2026-10-29"  # the date fact and compare claims are judged on
