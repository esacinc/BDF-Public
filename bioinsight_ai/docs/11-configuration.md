# Configuration (Environment Variables)

**In plain terms:** the app is configured entirely through environment
variables — no settings are hard-coded per environment. Locally they come from a
gitignored `.env` file; in deployed environments they come from **AWS Secrets
Manager**, written into a `.env.runtime` file that the container reads (see
[10-deployment.md](10-deployment.md)).

## How configuration is loaded

- **Code** — [config.py](../config.py) reads variables via `os.environ` and
  exposes them as module constants; `python-dotenv`'s `load_dotenv()` loads a
  local `.env` if present.
- **Local dev** — `.env` / [.env.dev](../.env.dev) / [.env.local](../.env.local)
  (all gitignored).
- **Deployed** — the CI pipeline pulls `bdf-chatbot-<env>-env` from Secrets
  Manager and writes `.env.runtime`, which `docker run --env-file` injects.

> **Secrets handling.** Variables marked **secret** below (AWS keys, JWT/Chainlit
> secrets, OAuth client secret, OpenAI key) must never be committed. The `.env*`
> files are gitignored for this reason; production values live only in Secrets
> Manager. This document intentionally lists **names and purpose only — no
> values.**

## Reference

### Environment & logging

| Variable | Purpose |
|---|---|
| `APP_ENV` | Runtime environment: `local` / `dev` / `stage` / `prod`. Drives CORS origins, cookie security, and environment-access checks. (`local` is treated as `dev`.) |
| `DEPLOY_ENV` | Deployment target label used by the CI/CodeDeploy scripts. |
| `LOG_LEVEL` | Logging verbosity (e.g. `warning`). |

### AWS credentials & region

| Variable | Purpose |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key. **Secret.** (Legacy `AWS_ACCESS_KEY` is accepted as a fallback.) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key. **Secret.** (Legacy `AWS_SECRET_KEY` fallback.) |
| `AWS_REGION` | AWS region (`us-east-1`). |

### Models (Bedrock & OpenAI)

| Variable | Purpose |
|---|---|
| `DEFAULT_MODEL` | Bedrock model ID for Claude (used by both LLM configs — see [02-workflow.md](02-workflow.md)). |
| `MODEL_ID` | Environment/model label (e.g. `bdf-chatbot-<env>`). |
| `OPENAI_API_KEY` | OpenAI API key. **Secret.** Present in the deployment secrets; the core chatbot uses Bedrock, so this is for OpenAI-backed functionality / parity with the imaging app (see [06-imaging-server.md](06-imaging-server.md)). |
| `OPENAI_MODEL_NAME` | OpenAI model name (paired with the key above). |

### Knowledge bases

(Literal IDs are documented in [05-knowledge-bases.md](05-knowledge-bases.md).)

| Variable | Purpose |
|---|---|
| `PUBLICATIONS_KB_ID` | CRDC / publications Bedrock Knowledge Base. |
| `MWB_KB_ID` | Metabolomics Workbench Knowledge Base. |
| `MWB_SOURCE_ID` | MWB KB data-source ID (retrieval filter). |

### DynamoDB tables

| Variable | Purpose |
|---|---|
| `DATA_LAYER_TABLE` | Conversation/thread history (Chainlit data layer). |
| `FEEDBACK_TABLE` | Feedback records. |
| `APPROVED_USERS_TABLE` | Approved user accounts. |
| `PENDING_USERS_TABLE` | Pending (awaiting-approval) accounts. |

Schemas: [12-data-and-persistence.md](12-data-and-persistence.md).

### S3 & CORS

| Variable | Purpose |
|---|---|
| `CHAINLIT_STORAGE_BUCKET` | S3 bucket for plots and chat attachments. |
| `ALLOWED_CORS_ORIGINS` | Comma-separated origins allowed to fetch presigned S3 URLs from the browser. |

### External data APIs

| Variable | Purpose |
|---|---|
| `GDC_BASE_API` | Base URL for the Genomic Data Commons REST API. |

### Auth, JWT & cookies

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | HS256 signing secret for the session JWT. **Secret.** |
| `JWT_ALGORITHM` | JWT algorithm (`HS256`). |
| `CHAINLIT_AUTH_SECRET` | Chainlit's auth secret. **Secret.** (Chainlit's own auth is disabled at runtime, but the value is still configured.) |
| `COOKIE_SECURE` | `1`/`0` — whether the `token` cookie is HTTPS-only. |
| `COOKIE_DOMAIN` | Domain scope for the auth cookie. |
| `OAUTH_GOOGLE_CLIENT_ID` | Google OAuth client ID. |
| `OAUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client secret. **Secret.** |
| `OAUTH_GOOGLE_REDIRECT_URI` | Google OAuth callback URL. |
| `APP_LOGIN_URL` | Base login URL used in emails and redirects. |
| `APP_LOGO_URL` | Logo URL used in admin/approval emails. |

Auth flow: [09-auth.md](09-auth.md).

### Chainlit & frontend

| Variable | Purpose |
|---|---|
| `CHAINLIT_HOST` | Host Chainlit binds/advertises. |
| `CHAINLIT_PORT` | Chainlit port (`8000`). |
| `CHAINLIT_URL` | Chainlit base URL. |
| `NEXT_PUBLIC_API_BASE` | API base URL **baked into the Next.js build** (see [10-deployment.md](10-deployment.md)). |
| `CHAINLIT_AUTH_DISABLE` | Set to `true` by [entrypoint.sh](../entrypoint.sh) (not from the env file) to disable Chainlit's built-in auth. |

### Non-env constants & legacy toggles

- `SES_SOURCE` — the transactional email sender, a hard-coded constant in
  [config.py](../config.py) (not an env var).
- `ENABLE_PASSWORD_AUTH`, `ENABLE_OAUTH` — feature toggles read only by the
  legacy [authentication.py](../authentication.py) stub, which is **not** part of
  the live auth flow (see [09-auth.md](09-auth.md)).
