# FastAPI-Crons Examples

This directory contains comprehensive examples demonstrating all features of the `fastapi-crons` library.

## Examples Overview

| Example | Description |
|---------|-------------|
| [basic_usage](./basic_usage/) | Simple cron job setup with async/sync functions |
| [advanced_hooks](./advanced_hooks/) | Custom hooks for logging, alerts, and metrics |
| [retry_and_timeout](./retry_and_timeout/) | Retry decorator with exponential backoff and job timeouts |
| [distributed_locking](./distributed_locking/) | Redis-based distributed locking for multi-instance deployments |
| [opentelemetry_integration](./opentelemetry_integration/) | OpenTelemetry tracing and metrics |
| [health_monitoring](./health_monitoring/) | Health check endpoint for monitoring systems |
| [full_featured](./full_featured/) | Complete application with all features combined |

## Running Examples

Each example can be run with:

```bash
cd examples/<example_name>
pip install fastapi-crons uvicorn
uvicorn app:app --reload
```

Then visit `http://localhost:8000/crons` to see registered jobs.

## Requirements

- Python 3.10+
- fastapi-crons
- uvicorn (for running examples)

For OpenTelemetry example:
```bash
pip install fastapi-crons[otel]
```

For distributed locking example:
```bash
# Requires Redis running on localhost:6379
docker run -d -p 6379:6379 redis:alpine
```
