#!/usr/bin/env python3
"""
run_frontend.py - Launches the Hype Arena Hackathon frontend.

Usage:
  python run_frontend.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from frontend.server import ThreadingHTTPServer, Handler
    port = int(os.getenv("PORT", "8000"))
    print(f"Hype Arena frontend on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
