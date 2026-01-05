# CHANGELOG


## v0.2.0 (2026-01-05)

### Bug Fixes

- Resolve all CI test failures and lint errors
  ([`1ce187a`](https://github.com/mincloff/fastapi-crons/commit/1ce187a9ae5516d0d719a7c2d21e94f24e898a57))

- Add requirements.txt with all project dependencies - Add comprehensive .gitignore including .venv
  - Fix test isolation by resetting global _global_crons state between tests - Fix all ruff lint
  errors (454 total fixed): - Remove unused imports and variables - Fix trailing whitespace in SQL
  strings - Update type annotations to use X | Y syntax - Fix exception chaining with 'from e' - Use
  specific exception types in tests - Fix variable redefinition in test_scheduler - Fix CI workflow
  syntax (continue-on-error was inside run block)

### Features

- Added health monitering and OpenTelemetry support
  ([`8df68b9`](https://github.com/mincloff/fastapi-crons/commit/8df68b9de71365c7c1ab568b759fb3549ad23bf2))


## v0.1.0 (2026-01-03)

### Bug Fixes

- **types**: Add complete type annotations for mypy strict mode compliance
  ([`997ce70`](https://github.com/mincloff/fastapi-crons/commit/997ce70aa930710165a76099339a10cd75d91c50))

- **types**: Add complete type annotations for mypy strict mode compliance
  ([`80cad6d`](https://github.com/mincloff/fastapi-crons/commit/80cad6d7fef1a831cecb8c9706b2454737a59aee))

### Features

- Add tests, scripts, and GitHub workflows
  ([`65fe770`](https://github.com/mincloff/fastapi-crons/commit/65fe770308a5d68ca8f7cf49c38ee0495d48a1ff))

Add comprehensive test suite, development scripts, and GitHub CI/CD configuration

- Add tests, scripts, and GitHub workflows
  ([`c6c0283`](https://github.com/mincloff/fastapi-crons/commit/c6c0283cad88b4d33a326ffef4618831133085d0))

Add comprehensive test suite, development scripts, and GitHub CI/CD configuration
