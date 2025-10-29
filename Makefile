.PHONY: help test lint format type-check dev build clean install-dev ci pre-commit setup

help:
	@echo "fastapi-crons development commands:"
	@echo ""
	@echo "  make setup          - Setup development environment"
	@echo "  make test           - Run tests with coverage"
	@echo "  make lint           - Run linting checks"
	@echo "  make format         - Format code"
	@echo "  make type-check     - Run type checking"
	@echo "  make dev            - Start development server"
	@echo "  make build          - Build package"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make ci             - Run full CI pipeline"
	@echo "  make pre-commit     - Run pre-commit checks"

setup:
	python scripts/setup_dev_env.py

test:
	bash scripts/test.sh

lint:
	bash scripts/lint.sh

format:
	bash scripts/format.sh

type-check:
	bash scripts/type-check.sh

dev:
	bash scripts/dev.sh

build:
	bash scripts/build.sh

clean:
	bash scripts/clean.sh

install-dev:
	bash scripts/install-dev.sh

ci:
	bash scripts/ci.sh

pre-commit:
	bash scripts/pre-commit.sh
