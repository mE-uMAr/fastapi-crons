[![Python CI](https://github.com/me-umar/fastapi-crons/actions/workflows/ci.yml/badge.svg)](https://github.com/me-umar/fastapi-crons/actions/workflows/ci.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/fastapi-crons)](https://pypi.org/project/fastapi-crons/)
[![GitHub Release](https://img.shields.io/github/v/release/me-umar/fastapi-crons)](https://github.com/me-umar/fastapi-crons/releases)

<h1                                                                                                                                                           
                                                                                                                                                                align="center"><strong>FASTAPI-CRONS</strong></h1>


<p align="center"><em>Effortlessly schedule and manage your background tasks.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/last%20commit-may-informational?style=flat-square" />
  <img src="https://img.shields.io/badge/python-100%25-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/languages-1-blue?style=flat-square" />
</p>

<br/>

<p align="center"><em>Built with the tools and technologies:</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/-Markdown-000000?style=flat-square&logo=markdown" />
  <img src="https://img.shields.io/badge/-Typer-000000?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/-TOML-bc4c3f?style=flat-square" />
  <img src="https://img.shields.io/badge/-FastAPI-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/-Python-306998?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/-AIOHTTP-2c5282?style=flat-square" />
  <img src="https://img.shields.io/badge/-Pydantic-d6336c?style=flat-square" />
</p>

<h1 align="center">FastAPI Crons – Developer Guide</h1>

Welcome to the official guide for using `fastapi_crons`, a high-performance, developer-friendly cron scheduling extension for FastAPI. This library enables you to define, monitor, and control scheduled background jobs using simple decorators and provides CLI tools, web-based monitoring, and SQLite-based job tracking.

---

## 🚀 Features

* Native integration with FastAPI using `from fastapi import FastAPI, Crons`
* Define cron jobs with decorators
* Async + sync job support
* SQLite job state persistence
* CLI for listing and managing jobs
* Automatic monitoring endpoint (`/crons`)
* Named jobs, tags, and metadata
* Easy to plug into any FastAPI project

---

## 📦 Installation

```bash
pip install fastapi-crons
```

---

## 🛠️ Quick Start

### 1. Setup FastAPI with Crons

```python
from fastapi import FastAPI
from fastapi_crons import Crons, get_cron_router

app = FastAPI()
crons = Crons(app)

app.include_router(get_cron_router())

@app.get("/")
def root():
    return {"message": "Hello from FastAPI"}

```

### 2. Define Cron Jobs

```python
@crons.cron("*/5 * * * *", name="print_hello")
def print_hello():
    print("Hello! I run every 5 minutes.")

@crons.cron("0 0 * * *", name="daily_task", tags=["rewards"])
async def run_daily_task():
    # Distribute daily rewards or any async task
    await some_async_function()
```
## Cron Expression overview
```bash
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of the month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
* * * * *
```
#### Examples:
- `* * * * *`: Every minute
- `*/15 * * * *`: Every 15 minutes
- `0 * * * *`: Every hour
- `0 0 * * *`: Every day at midnight
- `0 0 * * 0`: Every Sunday at midnight
---

## 🖥️ Cron Monitoring Endpoint

Once included, visit:

```
GET /crons
```

You'll get a full list of jobs with:

* `name`
* `expr` (cron expression)
* `tags`
* `last_run` (from SQLite)
* `next_run`

---

## 🧩 SQLite Job State Tracking

We use SQLite (via `aiosqlite`) to keep a persistent record of when each job last ran. This allows observability and resilience during restarts.

### Table:

```sql
CREATE TABLE IF NOT EXISTS job_state (
    name TEXT PRIMARY KEY,
    last_run TEXT
);
```
### Configuration
By default, job state is stored in a SQLite database named `cron_state.db` in the current directory. You can customize the database path:
```python
from fastapi_crons import Crons, SQLiteStateBackend

# Custom database path
state_backend = SQLiteStateBackend(db_path="/path/to/my_crons.db")
crons = Crons(state_backend=state_backend)
```

---

## 🧵 Async + Thread Execution

The scheduler supports both async and sync job functions
Jobs can be:

* `async def` → run in asyncio loop
* `def` → run safely in background thread using `await asyncio.to_thread(...)`

---

## 🧪 CLI Support

```bash
# List all registered jobs
fastapi-crons list

# Manually run a specific job
fastapi-crons run_job <job_name>
```

>

---
## 🧩 Advanced Features

* Distributed locking via Redis
* Retry policies
* Manual run triggers via HTTP
* Admin dashboard with metrics

### Job Tags

You can add tags to jobs for better organization:
```python
@cron_job("*/5 * * * *", tags=["maintenance", "cleanup"])
async def cleanup_job():
    # This job has tags for categorization
    pass
```

---

## ⚙️ Architecture Overview

```
FastAPI App
│
├── Crons()
│   ├── Registers decorated jobs
│   ├── Starts background scheduler (async)
│
├── SQLite Backend
│   ├── Tracks last run for each job
│
├── /crons endpoint
│   ├── Shows current job status (with timestamps)
│
└── CLI Tool
    ├── List jobs / Run manually
```

---

## 🧠 Contributing

We welcome PRs and suggestions! If you'd like this added to FastAPI officially, fork the repo, polish it, and submit to FastAPI with a clear integration proposal.

---

## 🛡️ Error Handling

* Each job has an isolated error handler
* Errors are printed and don't block scheduler
* Future: Add error logging / alert hooks

---

## 📄 License

[Licence](LICENSE)

---

#### Need help? Reach out:
[Email me](mailto:contact@meharumar.codes)

[github](https://github.com/me-umar)

## Read Documentation at:
[Documentation](https://crons.meharumar.codes)
---
## 💬 Credits

Made with ❤️ by Mehar Umar.  
Designed to give developers freedom, flexibility, and control when building production-grade FastAPI apps.

---
