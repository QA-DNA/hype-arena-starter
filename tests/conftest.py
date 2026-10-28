import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polygraph import pipeline  # noqa: E402
from polygraph.lexicon import Lexicon  # noqa: E402


@pytest.fixture(scope="session")
def lexicon():
    return Lexicon.load(ROOT / "data" / "lexicon.json")


@pytest.fixture(scope="session")
def bundle():
    return pipeline.Bundle.load()
