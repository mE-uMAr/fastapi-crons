# fastapi-crons-dashboard

Prebuilt web dashboard assets for [fastapi-crons](https://github.com/me-umar/fastapi-crons).

This package contains only the compiled single-file dashboard bundle. It exists
as a separate distribution so that the base `fastapi-crons` install does not
carry a large frontend build that most users never serve.

## Install

Do not install this directly. Install it through the `fastapi-crons` extra:

```bash
pip install fastapi-crons[dashboard]
```

The dashboard is then served at the `/dashboard` route of your cron router.

## License

MIT — see the [fastapi-crons repository](https://github.com/me-umar/fastapi-crons).
