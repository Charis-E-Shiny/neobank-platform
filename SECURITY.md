# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them privately through GitHub's
"Report a vulnerability" button on this repository (Security tab), or contact the maintainer
directly. Include steps to reproduce and the affected version or commit. We aim to acknowledge
reports within 5 business days.

## Scope and known limits

This project handles financial data patterns. Before any production use, review the following:

- **Authentication.** The API uses a single shared key (`API_KEY`). Use per-client keys, OAuth or
  mTLS for multi-tenant deployments. Rate limiting is not built in. Put the API behind your gateway.
- **Secrets.** Load `DATABASE_URL` and `API_KEY` from your platform's secret store. Never commit `.env`.
- **PII.** Credit decision logs store model features, not raw applicant data. Account owner names
  are stored in `accounts`. Apply your retention and deletion policy to those rows.
- **Transport.** Serve the API and frontend over HTTPS only. Use `sslmode=require` for PostgreSQL.
- **Idempotency keys.** Clients should generate unguessable references for payments.
- **Dependencies.** Pin and scan dependencies (for example, `pip-audit`, `npm audit`, OWASP
  Dependency-Check for the Java module) in CI.
