#!/bin/bash
# Run type checking with mypy

set -e

echo "🔎 Running type checks with mypy..."
python -m mypy fastapi_crons --strict

echo "✅ Type checking passed!"
