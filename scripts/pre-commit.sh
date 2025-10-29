#!/bin/bash
# Pre-commit hook - run checks before committing

set -e

echo "🔍 Running pre-commit checks..."

# Format check
python -m ruff format --check fastapi_crons tests || {
    echo "❌ Code formatting issues found. Run: ./scripts/format.sh"
    exit 1
}

# Linting
python -m ruff check fastapi_crons tests || {
    echo "❌ Linting issues found. Run: ./scripts/lint.sh"
    exit 1
}

# Tests
python -m pytest tests/ -q || {
    echo "❌ Tests failed!"
    exit 1
}

echo "✅ Pre-commit checks passed!"
