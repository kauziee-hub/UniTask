# AWS plan

Region: **ap-south-1 (Mumbai)**. Existing bucket: `unitask-ai-timetable-demo-2026-1931` (private, SSE-S3, Block Public Access on).
Existing IAM user: `unitask-demo-s3` (profile `unitask-demo`).

The rule: every AWS service has to do real work in the app. Nothing is there just for the architecture diagram.

## Status

| Service | What it does in UniTask | Status |
| --- | --- | --- |
| **S3** | Teacher handouts (`coursework/`), student submissions (`submissions/`), legacy timetable images (`timetables/`). Private objects; downloads use 5-minute presigned URLs. | **Code done.** IAM policy needs the two new prefixes (step 2 below) |
| **Cognito** | Student and teacher accounts. Set `AUTH_PROVIDER=cognito`; backend verifies Cognito ID tokens against the pool's JWKS. | **Code done**, unit-tested with a local RSA key. Needs a user pool (step 3), then a live test |
| **AWS Budgets** | Email alerts at $5 / $15 / $30 | Set up in step 1 |
| **SES** | "Due in 24h" and "Teams moved your deadline" emails | Next phase |
| **EventBridge Scheduler + Lambda** | Run Teams sync and deadline reminders on a schedule, replacing the in-process 30-minute loop when deployed | Next phase |
| **Secrets Manager** | `MS_CLIENT_SECRET` and `UNITASK_SECRET_KEY` (the key that encrypts stored Teams tokens) | With deployment |
| **Bedrock** | "Break this assignment into steps" from the Teams/handout instructions. Explanations only; ranking stays deterministic. Check which models are available in ap-south-1 (or via an APAC inference profile) before choosing one | Next phase |
| **CloudWatch** | Logs and alarms for sync failures | With deployment |
| **App Runner or EC2, RDS PostgreSQL, Amplify/CloudFront** | Hosting | Only after cost approval. Local dev needs none of this |

## Budget guardrails

- Budgets only alert. They don't stop spending, so watch anything that runs all the time (RDS, EC2, NAT gateways, public IPv4).
- S3, Cognito (small user counts), Budgets and SES sandbox usage at demo scale should cost close to nothing. **Check current pricing and your credit terms in the Billing console.** This plan hasn't verified them.
- Don't create anything that runs 24/7 until the app is ready to deploy.

## Steps that need the AWS Console

Paste the prompt below into Claude in Chrome while you're signed in to the AWS Console as an admin user
(not the `unitask-demo-s3` user).

---

```text
You are helping me set up AWS for my student project "UniTask". I am signed in to the AWS Console.
Work only in region ap-south-1 (Mumbai) unless a step says otherwise. Go step by step and show me what you
are about to create before each "Create" click. Do not delete or modify anything not listed here. Never
create access keys, never paste secrets into chat, and stop and ask me if anything would cost money beyond
the free usage tiers, or if a page looks different from what you expect.

STEP 1 — Billing safety (Billing and Cost Management → Budgets)
- Show me the current month's spend and the remaining credits (Billing → Credits). Report the credit
  amount, expiry date and which services they cover. Do not change anything there.
- Create a monthly cost budget named "unitask-monthly" for $30 with email alerts to me at 17% ($5),
  50% ($15) and 100% ($30) of ACTUAL spend. Use my account email unless I give another.

STEP 2 — Let the app store handouts and submissions (IAM → Users → unitask-demo-s3)
- Open the user's permissions. Find the policy that grants s3:PutObject / s3:GetObject on
  arn:aws:s3:::unitask-ai-timetable-demo-2026-1931/timetables/*.
- Show me that policy JSON first. Then edit it so the same actions (and s3:DeleteObject) also apply to:
    arn:aws:s3:::unitask-ai-timetable-demo-2026-1931/coursework/*
    arn:aws:s3:::unitask-ai-timetable-demo-2026-1931/submissions/*
  Keep every existing statement. Do not grant s3:* and do not touch bucket policy or Block Public Access.
- Confirm the bucket still shows "Block all public access: On" and default encryption SSE-S3.

STEP 3 — Accounts in Amazon Cognito (Cognito → User pools → Create user pool)
- Application type: "Traditional web application" or "Single-page application" — whichever lets me
  create an app client WITHOUT a client secret. Name the app client "unitask-web".
- Sign-in identifier: Email. Self-registration: enabled. Required attributes: email, name.
- Email delivery: "Send email with Cognito" (the free default, fine for a demo).
- MFA: off for now. Password policy: Cognito default.
- After creation, open the app client and make sure these auth flows are enabled:
  ALLOW_USER_PASSWORD_AUTH and ALLOW_REFRESH_TOKEN_AUTH. The client must have NO client secret.
- Name the user pool "unitask-users".
- Report back: User pool ID (looks like ap-south-1_XXXXXXX) and App client ID. These are not secrets.

STEP 4 — Report
Give me a short summary: what you created (with IDs/ARNs), what you changed, and anything you skipped and why.
```

---

## After Claude in Chrome finishes

1. On this laptop, configure the CLI profile (the CLI isn't installed yet):
   `winget install Amazon.AWSCLI`, then `aws configure --profile unitask-demo` with the
   `unitask-demo-s3` user's key, entered by you in the terminal and not pasted anywhere else.
   Then check it with `aws sts get-caller-identity --profile unitask-demo`.
2. In `backend/.env`:
   ```dotenv
   STORAGE_PROVIDER=s3
   S3_BUCKET=unitask-ai-timetable-demo-2026-1931
   AWS_REGION=ap-south-1
   AWS_PROFILE=unitask-demo
   # When you're ready to switch accounts to Cognito (existing local accounts won't carry over):
   AUTH_PROVIDER=cognito
   COGNITO_USER_POOL_ID=ap-south-1_XXXXXXX
   COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
3. Restart the backend. Register a new account: Cognito emails a code, which you enter on the sign-in page.
   Post an assignment with a handout. The object appears under `coursework/` in the bucket.

## Next phase (code, then a second Claude in Chrome session)

1. **Reminders.** Add a `reminders` table and an `/internal/run-reminders` job. Locally it runs in-process; in AWS, EventBridge Scheduler triggers a Lambda that calls it. Emails go through SES: verify the sender, and stay in the SES sandbox with verified recipients for the demo.
2. **Scheduled Teams sync** on the same Scheduler and Lambda, so syncing doesn't depend on the web server staying up.
3. **Bedrock step breakdown** on the assignment page, model ID configurable, with a token budget per request.
4. **Deploy:** container to App Runner (or one small EC2), RDS PostgreSQL (`DATABASE_URL` already supports it via psycopg), frontend to S3 + CloudFront or Amplify Hosting. Add the deployed callback URL to the Entra app's redirect URIs.
