#!/bin/bash
# CI/CD pipeline - run all checks

set -e

echo "🔄 Running CI pipeline..."

echo "1️⃣  Formatting check..."
python -m ruff format --check fastapi_crons tests

echo "2️⃣  Linting..."
python -m ruff check fastapi_crons tests

echo "3️⃣  Type checking..."
python -m mypy fastapi_crons --strict

echo "4️⃣  Running tests..."
python -m pytest tests/ -v --cov=fastapi_crons

echo "✅ CI pipeline passed!"
