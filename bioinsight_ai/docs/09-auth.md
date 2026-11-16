# Authentication & Authorization

**In plain terms:** users sign in with email/password or with Google. New
accounts don't get in automatically — an admin has to approve them first. Once
approved, the user gets a signed token (a JWT) stored in a browser cookie, and
that one token lets them through every part of the app (chat, admin panel) until
it expires. Admins can additionally restrict which environment (dev/stage/prod)
an account may use.

The FastAPI backend in [web_auth/](../web_auth/) (port 7000) is the **source of
truth** for auth. Chainlit's own auth is disabled; it just reads the same JWT.

> The legacy top-level [authentication.py](../authentication.py) is a near-empty
> stub (feature toggles only) and is **not** part of the live flow.

## The JWT and its cookie

Tokens are created and verified in
[web_auth/utils/security.py](../web_auth/utils/security.py):

- **Algorithm**: HS256, signed with `JWT_SECRET`.
- **Claims**: `sub` (the user's email, always lowercased), `role`
  (`user` / `admin`), `full_name`, `environment` (the `APP_ENV`), and `exp`.
- **Expiry**: ~1 day in the token's `exp`.
- **Cookie**: stored as a cookie named **`token`** with `HttpOnly` (no JS
  access), `Secure` (HTTPS-only, controlled by `COOKIE_SECURE`),
  `SameSite=Lax`, and a 7-day `max_age`.
- **Passwords**: hashed with **bcrypt** (`passlib`); never stored in plaintext.

Strong-password rules are enforced by `validate_password`: 12–64 chars, with
upper + lower + digit + special, and must not contain the email's username.

## Sign-in flows

### Email / password — `POST /auth/login`

1. Normalize the identifier to lowercase and look it up in the approved-users
   table.
2. Reject if the account is a Google account (`auth_provider == "google"`).
3. Verify the password against the bcrypt hash.
4. If `must_change_pw` is set (e.g. a freshly issued temp password), return
   `force_change_pw` so the UI sends the user to change their password.
5. **Environment check** — if the account has `allowed_environments` and the
   current `APP_ENV` isn't in it, return 403 (`local` is treated as `dev`).
6. Issue the JWT and set the `token` cookie.

### Google OAuth

- **`GET /auth/google/login`** → redirects to Google's consent screen
  (`client_id` = `OAUTH_GOOGLE_CLIENT_ID`, scope `openid email profile`,
  `redirect_uri` = `OAUTH_GOOGLE_REDIRECT_URI`).
- **`GET /auth/google/callback?code=...`** → exchanges the code with Google for
  an `id_token`, verifies it, and reads the email + name. Then:
  - **Approved Google user** → issue JWT, set cookie, **redirect to `/chat/`**.
  - **Existing password account** → redirect back to `/login` with an error
    (wrong sign-in method).
  - **Unknown user** → save them to the pending table (`auth_provider=google`),
    email the admins, and redirect with a "pending admin approval" message.

## Registration & approval workflow

New accounts are gated behind admin approval:

1. **`POST /auth/signup`** (password) — saves the applicant to
   `PENDING_USERS_TABLE` and notifies admins; the user lands back on `/login`.
   (Google sign-ups create a pending record via the callback above.)
2. **Admin panel** (Next.js `/admin`, admin-gated) calls the admin API
   ([admin_routes.py](../web_auth/admin_routes.py)):
   - **`GET /admin/pending-users`** — list applicants.
   - **`POST /admin/approve`** — moves the user into `APPROVED_USERS_TABLE` with
     a `role` and `allowed_environments`. Password users get a **temporary
     password** (flagged `must_change_pw`) emailed to them; Google users are
     approved without a password. An approval email is sent via SES.
   - **`POST /admin/deny`** — removes the pending record.
3. **Password self-service** — `POST /auth/change-password` and
   `POST /auth/forgot-password` (emails a temp password).

All emails go through SES with HTML templates in
[web_auth/templates/email/](../web_auth/templates/email/) (see
[07-aws-services.md](07-aws-services.md)). User records live in two DynamoDB
tables (`APPROVED_USERS_TABLE`, `PENDING_USERS_TABLE`) managed in
[web_auth/utils/dynamo.py](../web_auth/utils/dynamo.py); item shapes are in
[12-data-and-persistence.md](12-data-and-persistence.md).

## How requests are gated

One JWT guards three different surfaces:

| Surface | Gate | Mechanism |
|---|---|---|
| `/chat/*` (Chainlit) | Nginx `auth_request /auth_check` → **`GET /auth/verify`** | Decodes the `token` cookie and checks `exp`; 200 ⇒ allow, 401 ⇒ Nginx redirects to `/login` |
| `/admin` (Next.js admin panel) | Nginx `auth_request /admin_check` → **`GET /admin/verify`** | Same, **plus** requires `role == "admin"` (403 otherwise) via `require_admin_cookie` |
| Inside Chainlit | `@cl.header_auth_callback` | Decodes the *same* `token` cookie to build the `cl.User` (`sub`, `full_name`, `role`) — no extra round trip |
| Browser-side `/chat` | Next.js [middleware.ts](../frontend/app/middleware.ts) | Client-side JWT presence/expiry check, redirect to `/login` |

So Nginx is the authoritative server-side gate (see
[01-architecture.md](01-architecture.md)); the Next.js middleware is a
fast client-side pre-check; and Chainlit trusts the validated cookie to identify
the user (see [08-frontend-and-ui.md](08-frontend-and-ui.md)).

## Code map

| File | Responsibility |
|---|---|
| [web_auth/main.py](../web_auth/main.py) | FastAPI app, request logging, mounts `/auth` and `/admin` routers, root `/health` |
| [web_auth/auth_routes.py](../web_auth/auth_routes.py) | Login, signup, Google OAuth, `/auth/verify`, logout, change/forgot password |
| [web_auth/admin_routes.py](../web_auth/admin_routes.py) | `/admin/verify`, list pending, approve, deny |
| [web_auth/utils/security.py](../web_auth/utils/security.py) | JWT create/decode, bcrypt hash/verify, password validation |
| [web_auth/utils/dependencies.py](../web_auth/utils/dependencies.py) | FastAPI deps: bearer + cookie token extraction, `require_admin` / `require_admin_cookie` |
| [web_auth/utils/dynamo.py](../web_auth/utils/dynamo.py) | User-table CRUD (get/save/approve/deny) |
| [web_auth/utils/email.py](../web_auth/utils/email.py), [email_renderer.py](../web_auth/utils/email_renderer.py) | SES sending + HTML template rendering |

Relevant env vars (`JWT_SECRET`, `JWT_ALGORITHM`, `OAUTH_GOOGLE_*`,
`COOKIE_SECURE`, `APP_ENV`, `APP_LOGIN_URL`) are in
[11-configuration.md](11-configuration.md).
