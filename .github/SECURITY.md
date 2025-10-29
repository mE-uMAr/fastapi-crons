# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in FastAPI Crons, please email contact@meharumar.codes instead of using the issue tracker.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt of your report within 48 hours and provide an estimated timeline for a fix.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | ✅ Yes             |
| 1.x     | ⚠️ Limited support |
| < 1.0   | ❌ No              |

## Security Best Practices

When using FastAPI Crons:

1. **Keep dependencies updated** - Regularly update FastAPI, croniter, and other dependencies
2. **Use environment variables** - Store sensitive configuration in environment variables, not in code
3. **Validate cron expressions** - Always validate user-provided cron expressions
4. **Secure Redis connections** - If using Redis for distributed locking, use authentication and encryption
5. **Monitor job execution** - Regularly review job logs and execution history
6. **Limit job permissions** - Run jobs with minimal required permissions

## Security Updates

Security updates will be released as soon as possible after a vulnerability is confirmed. We recommend:

- Subscribing to release notifications
- Regularly checking for updates
- Testing updates in a staging environment before production deployment
