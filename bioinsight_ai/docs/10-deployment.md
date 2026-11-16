# Deployment

**In plain terms:** the whole application is packaged into a single Docker
image. Jenkins builds that image, pushes it to AWS's container registry (ECR),
and tells AWS CodeDeploy to roll it out onto EC2 servers. Which environment it
deploys to (dev / stage / prod) is decided by the branch (and, for prod, a
version tag). Runtime secrets are pulled from AWS Secrets Manager at build time —
never stored in the repo.

This doc covers the hosting/CI-CD plane. The runtime AWS services the app *calls*
(Bedrock, DynamoDB, S3, SES) are in [07-aws-services.md](07-aws-services.md);
the four processes inside the container are in [01-architecture.md](01-architecture.md).

## The Docker image

A multi-stage build ([Dockerfile](../Dockerfile)) produces one image that
contains everything:

1. **Builder** (`python:3.11`) — installs Node.js, runs `npm ci` + `npm run
   build` for the Next.js frontend (baking in `NEXT_PUBLIC_API_BASE`), and
   creates a Python venv with the scientific stack (`numpy`/`scipy`/
   `scikit-learn`) plus [requirements.txt](../requirements.txt).
2. **s5cmd builder** (`golang`) — rebuilds the `s5cmd` binary from source to
   avoid a vulnerable version that ships with the pip package.
3. **Runtime** (`python:3.11-slim`) — installs Node.js + **nginx**, copies the
   venv, the built frontend, the app code, and [nginx.conf](../nginx.conf);
   installs the frontend production deps and
   [requirements_python311.txt](../requirements_python311.txt); swaps in the
   rebuilt `s5cmd`; and sets `ENTRYPOINT ["./entrypoint.sh"]`. Exposes ports
   `80` and `3000`.

At container start, [entrypoint.sh](../entrypoint.sh) launches the four
processes (Nginx, Chainlit, FastAPI, Next.js) — see
[01-architecture.md](01-architecture.md).

## CI/CD pipeline (Jenkins)

[Jenkinsfile](../Jenkinsfile), with `DOCKER_BUILDKIT=1`:

| Stage | What it does |
|---|---|
| **Disk Space Check** | Fails/prunes Docker cache if the agent is low on disk |
| **Checkout & Set DEPLOY_ENV** | Maps branch → environment: `dev` branch → **dev**, the stage branch → **stage**, `main` **only when tagged `vX.Y.Z`** → **prod** (untagged `main` is skipped) |
| **Load Secrets & Write .env.runtime** | Reads `bdf-chatbot-<env>-env` from **AWS Secrets Manager** and writes a `.env.runtime` file with all runtime config |
| **Build & Push to ECR** | `docker buildx build` with registry cache (`<repo>:cache`), tags `:latest`, pushes to the per-env ECR repo `bdf-chatbot-<env>` |
| **Package AppSpec & Scripts** | Zips [appspec.yml](../appspec.yml) + [scripts/](../scripts/) + `.env.runtime` |
| **Upload to S3** | Uploads the zip to `s3://bdf-chatbot-deployments/<env>/bdf-chatbot.zip` |
| **Deploy with CodeDeploy** | `aws deploy create-deployment` (app `BDF-Chatbot-CodeDeploy`, group `BDF-Chatbot-<env>-Deployment-Group`, config `AllAtOnce`) and waits for success |

Secrets, the ECR repo, the deployment bucket, and the CodeDeploy app/group are
all per-environment. Account IDs are resolved at runtime
(`aws sts get-caller-identity`), so no account ID is hard-coded.

## Deployment on the EC2 host (CodeDeploy)

The target is **EC2 instances running Ubuntu** (the CodeDeploy hooks `runas:
ubuntu` and the app lives at `/home/ubuntu/BDF-Chatbot`). [appspec.yml](../appspec.yml)
copies `.env.runtime` to the host and runs lifecycle scripts from
[scripts/](../scripts/):

| Hook | Script | Action |
|---|---|---|
| `ApplicationStop` | [stop_server.sh](../scripts/stop_server.sh) | Stop & remove the running container, `docker system prune` |
| `BeforeInstall` | [cleanup_target.sh](../scripts/cleanup_target.sh) | Clean the target directory / reclaim disk |
| `AfterInstall` | [generate_salutation.sh](../scripts/generate_salutation.sh) | Best-effort pre-warm of the cached opening message (`docker exec … opening_message`; skips if no container) — see [08-frontend-and-ui.md](08-frontend-and-ui.md) |
| `ApplicationStart` | [start_server.sh](../scripts/start_server.sh) | ECR login, `docker pull :latest`, `docker run` the container |
| `ValidateService` | [validate_service.sh](../scripts/validate_service.sh) | Health-check the three services with retries |

### How the container is run

`start_server.sh` runs the image with:
- `--env-file .env.runtime` (all runtime config)
- **CloudWatch logs** — `awslogs` driver, group `/bdf-chatbot/<env>`
- resource limits — `--memory 7g --cpus 2`
- `--restart unless-stopped`
- **port mapping** — `80:80` for stage/prod, `8080:80` for dev

`validate_service.sh` then polls, expecting healthy responses from the Next.js
frontend (`/chat/` → 200/302), the FastAPI backend (`/api/auth/verify` →
200/401), and Chainlit (`/chat/` → 200/302) before the deployment is marked
successful.

## Environments

| Environment | Trigger | External port |
|---|---|---|
| **dev** | `dev` branch | `8080` |
| **stage** | stage branch | `80` |
| **prod** | `main` tagged `vX.Y.Z` | `80` |

`APP_ENV` (and `DEPLOY_ENV`) flow from the environment's secret into the
container and drive environment-specific behavior (CORS origins, cookie
security, environment-access checks).

## Local development

[run_local.sh](../run_local.sh) / [run_local.bat](../run_local.bat) bring up the
stack locally. `entrypoint.sh` recognizes `APP_ENV=local` (treated like `dev`
for access control). Local config comes from the gitignored `.env` /
[.env.dev](../.env.dev) / [.env.local](../.env.local) files rather than Secrets
Manager. The full env var reference is in
[11-configuration.md](11-configuration.md).
