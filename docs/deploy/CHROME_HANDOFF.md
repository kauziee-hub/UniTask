# UniTask 3.0 — AWS deployment handoff for Claude Chrome

Paste this whole file into Claude Chrome (the session with AWS console access).
Claude Code (on the laptop) builds and tests the app and pushes it to GitHub. Claude Chrome creates
the AWS resources and deploys. **Region for everything: Asia Pacific (Mumbai) `ap-south-1`.**

## Architecture (decided — please don't substitute)

| Need | Service | Why |
| --- | --- | --- |
| Website + API | **One Docker container** on **Amazon ECS Express Mode** (Fargate + HTTPS load balancer, URL `https://<service>.ecs.ap-south-1.on.aws`) | The container serves both the React site and the FastAPI API from one origin, so there are no CORS or mixed-content problems. App Runner is closed to new customers since 30 April 2026. |
| Image build | **AWS CloudShell** → **Amazon ECR** | The GitHub repo `rith758/UniTaskAI` is public, so CloudShell can clone it without a GitHub app. CloudShell has Docker. |
| Database | **Amazon RDS for PostgreSQL 16**, private, in the default VPC | Persistent, relational, matches the app's migrations. |
| Files | **Amazon S3** (private bucket, presigned links) | Already supported by the app. |
| AI | **Amazon Bedrock** (Amazon Nova via the APAC inference profile) | Real inference for the tutor, Q&A, syllabus extraction, flashcards and grading. |
| OCR | **Amazon Textract** `DetectDocumentText` | Scanned pages and photos. |
| Reminders | **Amazon EventBridge** rule → API destination → `POST /internal/cron/reminders` | ECS has no cron. |
| Email | **Amazon SES** (sandbox is fine: verify the sender and the demo recipient) | Deadline reminder emails. |
| Logs | **CloudWatch Logs** (automatic with ECS) | Monitoring. |

Nothing in the app needs AWS access keys. Every AWS call uses the **ECS task role**.

---

## Phase 1 — start now (doesn't depend on the code)

### 1. RDS PostgreSQL (takes ~10 minutes to create, so do it first)

RDS → Create database:
- Standard create · PostgreSQL · engine version 16.x · Template **Free tier** (or Dev/Test)
- DB instance identifier: `unitask-db`
- Master username: `unitask`
- Password: **letters and digits only** (no `@ : / ? # %`), 24+ characters. Generate one in CloudShell:
  `python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(28)))"`
  Keep it for step 9. Don't paste it into chat logs or GitHub.
- Instance class: `db.t4g.micro` · Storage 20 GiB gp3, autoscaling off
- Connectivity: default VPC · **Public access: No** · VPC security group: **Create new** → `unitask-db-sg`
- Additional configuration → **Initial database name: `unitask`** · backups 1 day · deletion protection off
- After it's created: EC2 → Security groups → `unitask-db-sg` → Inbound rules → edit the PostgreSQL rule so the
  source is the **default VPC CIDR** (VPC console → default VPC → IPv4 CIDR, usually `172.31.0.0/16`).
- Record the **endpoint** (e.g. `unitask-db.xxxx.ap-south-1.rds.amazonaws.com`).

### 2. S3 bucket

Reuse the existing bucket `unitask-ai-timetable-demo-2026-1931` if it exists in ap-south-1 (it holds the original
timetable uploads; **don't delete anything in it**). Otherwise create `unitask-files-<account-id>`.
Block all public access: **on**. Default encryption SSE-S3. No bucket policy needed.

### 3. Bedrock

Bedrock console (ap-south-1) → Playground/Chat → pick **Amazon Nova Lite** and send "hello". Then **Amazon Nova Pro**.
If a model needs access enabled, enable it (Model access page). Then Bedrock → **Cross-region inference** and record the
inference profile IDs. Expected:
- `apac.amazon.nova-pro-v1:0` (main model)
- `apac.amazon.nova-lite-v1:0` (fast model)

If Anthropic Claude is already enabled in this account you may use its `apac.anthropic...` profile as the main model instead.

### 4. SES (optional but wanted)

SES → Verified identities → Create identity → Email address → the email the student demo will use, and the sender
address (can be the same). Click the verification link in that inbox. Sandbox mode is fine for the demo.

### 5. ECR repository

ECR → Create repository → Private → name `unitask` → defaults.

### 6. IAM roles

a. **Task execution role**: `ecsTaskExecutionRole` with the AWS managed policy `AmazonECSTaskExecutionRolePolicy`
   (the ECS Express Mode console can create it for you).

b. **Infrastructure role** for Express Mode (the console's "Create new role" option creates it).

c. **Task role** `unitask-task-role` — IAM → Roles → Create role → AWS service → Elastic Container Service →
   **Elastic Container Service Task** → no managed policies → name it → then add this inline policy
   (replace `BUCKET`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "Files", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": "arn:aws:s3:::BUCKET/*"},
    {"Sid": "ListFiles", "Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::BUCKET"},
    {"Sid": "Bedrock", "Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"], "Resource": "*"},
    {"Sid": "Ocr", "Effect": "Allow", "Action": ["textract:DetectDocumentText"], "Resource": "*"},
    {"Sid": "Email", "Effect": "Allow", "Action": ["ses:SendEmail", "ses:SendRawEmail"], "Resource": "*"}
  ]
}
```

### 7. Two secrets (generate in CloudShell, keep for step 9)

```bash
python3 -c "import secrets;print('UNITASK_SECRET_KEY', secrets.token_urlsafe(48))"
python3 -c "import secrets;print('CRON_SECRET', secrets.token_urlsafe(32))"
```

**Report back to the user** (they relay it to Claude Code): RDS endpoint, bucket name, Bedrock profile IDs that worked,
SES identity status, ECR repository URI. Never report the passwords or secrets in chat.

---

## Phase 2 — after Claude Code pushes the release branch

Claude Code will give the user a **branch name and commit SHA** (branch `release/unitask-3`).

### 8. Build and push the image (CloudShell, ap-south-1)

```bash
REGION=ap-south-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/unitask
rm -rf UniTaskAI && git clone --depth 1 --branch release/unitask-3 https://github.com/rith758/UniTaskAI.git && cd UniTaskAI
git log -1 --format=%H            # must equal the SHA Claude Code gave
TAG=$(git rev-parse --short HEAD)
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker build -t $REPO:$TAG -t $REPO:latest .
docker push $REPO:$TAG && docker push $REPO:latest
echo $REPO:$TAG
```

If CloudShell runs out of space: `docker system prune -af` and retry.

### 9. ECS Express Mode service

ECS console → **Express mode** → Create:
- Image URI: `<REPO>:<TAG>` from step 8
- Service name: `unitask`
- Task execution role: `ecsTaskExecutionRole` · Infrastructure role: the Express Mode role · **Task role: `unitask-task-role`**
- Container port: **8000** · Health check path: **`/health`**
- CPU 1 vCPU · Memory 2 GB · Desired/min tasks 1, max 2
- Network: default VPC (public subnets are fine; tasks need outbound internet for Bedrock/S3)
- Environment variables (plain values; `<…>` are from phase 1):

| Name | Value |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://unitask:<RDS_PASSWORD>@<RDS_ENDPOINT>:5432/unitask?sslmode=require` |
| `UNITASK_SECRET_KEY` | from step 7 |
| `CRON_SECRET` | from step 7 |
| `AUTH_PROVIDER` | `local` |
| `STORAGE_PROVIDER` | `s3` |
| `S3_BUCKET` | bucket from step 2 |
| `AWS_REGION` | `ap-south-1` |
| `LLM_PROVIDER` | `bedrock` |
| `BEDROCK_MODEL_ID` | e.g. `apac.amazon.nova-pro-v1:0` |
| `BEDROCK_FAST_MODEL_ID` | e.g. `apac.amazon.nova-lite-v1:0` |
| `OCR_PROVIDER` | `textract` |
| `EMAIL_PROVIDER` | `ses` (or `log` if SES isn't verified) |
| `SES_FROM_ADDRESS` | the verified sender |
| `JOB_QUEUE` | `inline` |
| `SCHEDULER` | `external` |
| `SEED_DEMO` | `true` (creates the clearly-labelled synthetic demo accounts once) |
| `LOG_LEVEL` | `INFO` |

After the service is up, note its URL `https://unitask.ecs.ap-south-1.on.aws` (or similar) and add two more variables,
then update the service: `CORS_ORIGINS=<that URL>` and `FRONTEND_URL=<that URL>`.

Do **not** set `AWS_PROFILE`, `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY`.

### 10. Verify

- `https://<URL>/health` → `{"status":"ok","version":"3.0.0"}`
- `https://<URL>/api/ai/status` → `"provider":"bedrock"`, `"available":true`
- Open `https://<URL>/` → sign in as `riya.sharma@example.edu` / `demo-student-2026` (synthetic demo account).
- CloudWatch → Log groups → the ECS service's log group shows `Database schema at revision 0003` (or later).

### 11. EventBridge reminders

EventBridge → API destinations → Create:
- Connection: authorization type **API key**, key name `X-Cron-Secret`, value = `CRON_SECRET`
- Endpoint `https://<URL>/internal/cron/reminders`, method POST, rate limit 1/sec
Then Rules → Create rule → **Schedule** → rate 30 minutes → target **EventBridge API destination** → the one above
(let it create the role). Optional second rule for `/internal/cron/sync_all` every 60 minutes.

### 12. Redeploying a new commit

Repeat step 8 with the new branch/SHA, then ECS → the Express service → **Update** → new image URI → Update.

## What to report back each time

URL, image tag, commit SHA deployed, `/health` and `/api/ai/status` output, and the last 20 log lines if anything fails.
