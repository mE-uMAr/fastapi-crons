#!/bin/bash
# Run all tests with coverage report

set -e

echo "🧪 Running tests with pytest..."
python -m pytest tests/ -v --cov=fastapi_crons --cov-report=html --cov-report=term-missing

echo "✅ Tests completed! Coverage report generated in htmlcov/index.html"
