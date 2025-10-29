#!/bin/bash
# Run linting and code quality checks

set -e

echo "🔍 Running ruff check..."
python -m ruff check fastapi_crons tests

echo "🔍 Running ruff format check..."
python -m ruff format --check fastapi_crons tests

echo "✅ Linting passed!"
