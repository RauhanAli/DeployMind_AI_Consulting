# Security

## Authentication

* **Passwords:** bcrypt (cost 12). Policy: ≥10 characters, at least one letter and one digit (enforced in the
  API and mirrored in the UI).
* **Access tokens:** JWT (HS256), 15-minute TTL, held **in memory only** in the browser.
* **Refresh tokens:** opaque random 48-byte tokens, stored as SHA-256 hashes, sent as an `httpOnly`,
  `SameSite=Lax` cookie scoped to `/api/v1/auth` (`Secure` when `COOKIE_SECURE=true`). They **rotate on every
  use**. Reusing a rotated token revokes the whole token family (theft detection).
* Login failures return one generic error whether or not the account exists, and are audited.
* `APP_ENV=production` refuses to boot with the development JWT secret, the development encryption key,
  `COOKIE_SECURE=false` or mock AI (`Settings._production_guards`).

## Authorisation (RBAC, enforced in the backend)

Roles and permissions are defined once in `app/core/rbac.py` and synced into `roles`, `permissions` and
`role_permissions` at startup.

| Role | Scope | Summary |
| --- | --- | --- |
| Super Admin | internal | everything |
| Organisation Admin | internal or customer | internal: all tenants minus platform settings; customer: manage own members |
| Project Manager | internal | delivery, proposals (incl. approval), support management, budgets |
| Engineer | internal | discovery, architecture (incl. review), build, deploy (not approve), evaluations, incidents |
| Customer | customer | own org: assessments, proposals (decide), projects (read), assistant, documents, tickets |
| Viewer | internal or customer | read-only |

`CUSTOMER_FORBIDDEN` strips internal-only permissions from any customer membership, whatever role it holds.
Frontend navigation hides what a user cannot do, but **every check is enforced in the API** (see
`tests/test_auth_rbac.py`).

Additional business rules:
* An AI-generated proposal cannot be approved by its author. A different authorised reviewer is required.
* Production deployments require `deployment.approve` from someone other than the person who triggered them
  (four-eyes). Only a super admin can remove the production approval gate.
* Customers never see internal comments, internal documents, AI provenance, draft proposals, or tasks and
  milestones not marked customer-visible.

## Tenant isolation

* `Principal.org_ids()` is `None` for provider staff (all tenants, filtered by permission) or the user's customer
  org ids.
* `get_scoped(db, Model, id, principal, permission)` loads a row **only within scope** and returns **404** for
  out-of-scope ids, so existence never leaks.
* List endpoints apply `principal.scope_filter(stmt, Model)`.
* Retrieval applies the tenant filter and document visibility (`organisation` / `internal` / `restricted` +
  `document_permissions`) **inside the SQL**, so unauthorised chunks are never loaded.
* Conversations are private to their owner (customer org admins cannot read colleagues' chats).
* The runtime API for deployed containers authenticates with a per-deployment token (stored hashed, revoked when
  the deployment is superseded). Anonymous end users only reach organisation-wide documents.

`tests/test_tenant_isolation.py` calls 20 read endpoints and 9 write endpoints with another tenant's ids, checks
listings, internal endpoints and cross-tenant retrieval, and asserts no content leaks. Playwright repeats the
URL-tampering check in the browser.

## Secrets management

* `app/core/secrets.py` defines a `SecretBackend` protocol. The default `FernetBackend` encrypts with
  `SECRETS_ENCRYPTION_KEY` (AES-128-CBC + HMAC). The `secrets` table stores ciphertext and a 4-character hint.
* Integration credentials and environment secrets are **write-only**: no endpoint returns them. They're
  decrypted server-side at call or deploy time and injected into containers as environment variables.
* Integration `config` rejects credential-like keys (`password`, `token`, `api_key`…), and environment variables
  reject sensitive or reserved names. Both point to the secrets endpoints.
* To use AWS Secrets Manager or Vault, implement `encrypt` / `decrypt` (or reference-based get/put) behind the same
  protocol and select it with `SECRETS_BACKEND`.

## Input, upload and transport security

* Pydantic validation on every request body. Consistent `validation_error` envelope.
* **Uploads:** extension allow-list **and** magic-byte sniffing (PDF `%PDF-`, DOCX zip structure with a
  zip-bomb size check, UTF-8 text), size limit (`MAX_UPLOAD_MB`), path-stripped safe filenames, random storage
  keys, SHA-256 dedupe. Attachments are served with `Content-Disposition: attachment` and `nosniff`.
* **SSRF:** integration URLs are resolved and link-local / cloud-metadata ranges are always blocked. Private
  ranges are blocked when `APP_ENV=production`.
* **Webhooks:** HMAC-SHA256 signature over the raw body (`X-DeployMind-Signature: sha256=…`), compared in
  constant time. Rejected attempts are logged as integration runs.
* **PostgreSQL connector:** runs in a `READ ONLY` transaction with a connect timeout and a row cap.
* **Prompt injection:** retrieved content is passed as numbered data passages with an instruction to treat it as
  data. Answers without valid citations are discarded in grounded mode, and agents cannot choose tools.
* **Headers:** `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP,
  restrictive CSP on API responses, HSTS when `COOKIE_SECURE=true`. The web app sets the same headers.
* **CORS:** explicit origin allow-list (`CORS_ORIGINS`), credentials allowed only for those origins.
* **Rate limiting:** Redis fixed window per IP, `RATE_LIMIT_PER_MINUTE` for the API and
  `AUTH_RATE_LIMIT_PER_MINUTE` (default 10) for login, register and refresh. Falls back to in-process counters if
  Redis is down.

## Audit logging

`audit_logs` records actor, action, resource, organisation, details, IP and request id for authentication events,
membership changes, settings, assessments, proposals (each transition and customer decision), requirements,
architecture reviews, documents, integrations, credentials (never values), deployments (trigger, approve,
reject, rollback, stop), incidents, tickets, budgets and pricing. It's visible under **Audit Logs**
(`audit.read`).

## Known limitations

* MFA and SSO (OIDC/SAML) are not implemented. Integrate an IdP in front of `/auth` for production.
* Rate limiting is per IP. Add per-account throttling and lockout for internet-facing deployments.
* The local Docker adapter requires access to the Docker socket (root-equivalent). Use it for local demos only;
  production should use the ECS adapter.
* Backend static typing (mypy) runs as advisory in CI (Optional narrowing on ORM lookups). The frontend
  (`tsc --noEmit`) is strict and blocking.

## Reporting

Report security issues privately to the maintainers. Do not open public issues for vulnerabilities.
