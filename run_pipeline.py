#!/usr/bin/env python3
"""
Root-level wrapper for Hype Arena pipeline in src/.
Runs Layers 1-4:
- Layer 1: Fuzzy Entity Resolution
- Layer 2: Temporal Interval Algebra Knowledge Base
- Layer 3: Symbolic Constraint Engine
- Layer 4: Calibrated Bayesian Scoring
"""
import os
import sys

# Add src/ directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from run_pipeline import main

if __name__ == "__main__":
    main()
