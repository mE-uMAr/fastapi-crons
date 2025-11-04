# Contributing to FastAPI Crons

Thank you for your interest in contributing to FastAPI Crons! We welcome contributions from the community. This document provides guidelines and instructions for contributing.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a welcoming environment for all contributors.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- pip

### Setup Development Environment

1. Fork the repository on GitHub
2. Clone your fork locally:
   \`\`\`bash
   git clone https://github.com/me-umar/fastapi-crons.git
   cd fastapi-crons
   \`\`\`

3. Create a virtual environment:
   \`\`\`bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   \`\`\`

4. Install development dependencies:
   \`\`\`bash
   python scripts/setup_dev_env.py
   # or
   pip install -e ".[dev]"
   \`\`\`

## Development Workflow

### Creating a Branch

Create a feature branch for your work:
\`\`\`bash
git checkout -b feature/your-feature-name
# or for bug fixes
git checkout -b fix/your-bug-fix
\`\`\`

### Making Changes

1. Make your changes in the appropriate files
2. Write or update tests for your changes
3. Ensure all tests pass:
   \`\`\`bash
   make test
   # or
   pytest tests/
   \`\`\`

4. Format and lint your code:
   \`\`\`bash
   make format
   make lint
   \`\`\`

5. Run type checking:
   \`\`\`bash
   make type-check
   \`\`\`

### Commit Guidelines

- Use clear, descriptive commit messages
- Reference issues when applicable (e.g., "Fixes #123")
- Keep commits atomic and focused
- Example: `feat: add retry policy for failed jobs`

### Commit Message Format

\`\`\`
<type>(<scope>): <subject>

<body>

<footer>
\`\`\`

**Types:**
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring without feature changes
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Build process, dependencies, or tooling changes

**Example:**
\`\`\`
feat(scheduler): add exponential backoff retry policy

Implement exponential backoff for failed job executions.
Allows configuration of max retries and backoff multiplier.

Fixes #456
\`\`\`

## Testing

### Running Tests

\`\`\`bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=fastapi_crons --cov-report=html

# Run specific test file
pytest tests/test_scheduler.py

# Run specific test
pytest tests/test_scheduler.py::test_job_registration
\`\`\`

### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names: `test_<function>_<scenario>`
- Use fixtures from `conftest.py`
- Test both sync and async functionality
- Aim for >80% code coverage

Example:
\`\`\`python
@pytest.mark.asyncio
async def test_scheduler_executes_job_at_correct_time(scheduler):
    """Test that scheduler executes jobs at the correct time."""
    executed = False
    
    @scheduler.cron("* * * * *")
    async def test_job():
        nonlocal executed
        executed = True
    
    await scheduler.start()
    await asyncio.sleep(1)
    await scheduler.stop()
    
    assert executed
\`\`\`

## Code Style

We use:
- **Ruff** for linting and formatting
- **MyPy** for type checking
- **Black** style for code formatting

### Format Your Code

\`\`\`bash
make format
\`\`\`

### Check Linting

\`\`\`bash
make lint
\`\`\`

### Type Checking

\`\`\`bash
make type-check
\`\`\`

## Documentation

- Update `README.md` for user-facing changes
- Add docstrings to all public functions and classes
- Use Google-style docstrings:

\`\`\`python
def schedule_job(cron_expr: str, name: str) -> CronJob:
    """Schedule a new cron job.
    
    Args:
        cron_expr: Cron expression (e.g., "0 0 * * *")
        name: Unique job name
        
    Returns:
        CronJob: The scheduled job instance
        
    Raises:
        ValueError: If cron expression is invalid
    """
\`\`\`

## Pull Request Process

1. Update the `README.md` with details of changes if applicable
2. Ensure all tests pass and coverage is maintained
3. Update documentation as needed
4. Create a pull request with a clear description:
   - What problem does this solve?
   - How does it solve it?
   - Any breaking changes?
   - Related issues

5. Link related issues in the PR description
6. Wait for code review and address feedback

### PR Title Format

Follow the same format as commit messages:
- `feat: add job retry mechanism`
- `fix: correct timezone handling in cron expressions`
- `docs: update installation instructions`

## Reporting Issues

### Bug Reports

Include:
- Python version
- FastAPI Crons version
- Minimal reproducible example
- Expected vs actual behavior
- Error traceback if applicable

### Feature Requests

Include:
- Use case and motivation
- Proposed solution (if any)
- Alternative approaches considered
- Examples of similar features in other projects

## Questions?

- Open a discussion on GitHub
- Check existing issues and discussions
- Email: contact@meharumar.codes

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to FastAPI Crons! 🎉
