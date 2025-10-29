#!/bin/bash
# Clean up build artifacts and cache files

set -e

echo "🧹 Cleaning up..."

# Remove build artifacts
rm -rf build/
rm -rf dist/
rm -rf *.egg-info
rm -rf .eggs/

# Remove Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
find . -type f -name "*.egg-link" -delete

# Remove test cache
rm -rf .pytest_cache/
rm -rf .coverage
rm -rf htmlcov/

# Remove mypy cache
rm -rf .mypy_cache/

# Remove ruff cache
rm -rf .ruff_cache/

echo "✅ Cleanup completed!"
