# Demonstration release for Claude Chrome

Use **kauziee-hub/UniTask**, branch **release/unitask-3**. This branch includes the complete student UI, the tutor crash fix, password-free demo entry, and a GitHub Actions container build. Do not deploy the old e337ee5 backend-only commit.

## Image build (replaces CloudShell and CodeBuild)

Every push runs `.github/workflows/image.yml`: frontend lint/build, backend tests against SQLite and PostgreSQL 16, Docker build for **Linux x86_64**, then a running-container smoke test before publishing.

Actions: https://github.com/kauziee-hub/UniTask/actions

Successful runs publish `ghcr.io/kauziee-hub/unitask:<full-commit-sha>`, the seven-character SHA tag, and `:latest`. Deploy the immutable SHA tag shown in the successful run summary. No AWS keys or extra GitHub secrets are needed for the build.

**One-time package setting:** GitHub profile → Packages → unitask → Package settings → Change visibility → Public. Repository visibility does not make a new GHCR package public automatically. Confirm anonymous pull works before configuring ECS. The image contains public application code; credentials are supplied only at runtime.

## AWS configuration

Keep the RDS PostgreSQL database, private S3 bucket, ECS task role and ECS Express service from CHROME_HANDOFF.md. Container port **8000**, health path **/health**, architecture **X86_64**, one task for this demonstration. Use these overrides:

| Variable | Value |
| --- | --- |
| DEMO_MODE | true |
| SEED_DEMO | true |
| AUTH_PROVIDER | local |
| STORAGE_PROVIDER | s3 |
| S3_BUCKET | unitask-files-888583764945 |
| AWS_REGION | ap-south-1 |
| DATABASE_URL | User enters the RDS PostgreSQL URL with sslmode=require |
| UNITASK_SECRET_KEY | User enters a stable random secret |
| LLM_PROVIDER | gemini |
| GEMINI_API_KEY | User enters privately |
| LLM_MODEL | gemini-3.5-flash |
| LLM_FAST_MODEL | gemini-flash-lite-latest |
| BEDROCK_MODEL_ID | apac.amazon.nova-pro-v1:0 |
| BEDROCK_FAST_MODEL_ID | apac.amazon.nova-lite-v1:0 |
| EMAIL_PROVIDER | log |
| OCR_PROVIDER | llm |
| JOB_QUEUE | inline |
| SCHEDULER | internal |
| FRONTEND_URL | The actual HTTPS service URL |
| CORS_ORIGINS | The actual HTTPS service URL |

No Cognito signup or SES verification is required. The internal scheduler works with one running API worker/task, so EventBridge is optional. If EventBridge is configured later, use SCHEDULER=external and set CRON_SECRET. Keep max tasks at 1 while using the internal scheduler to avoid duplicate scheduled jobs.

Do not set AWS_PROFILE or static AWS keys in ECS. Attach unitask-task-role. The database must be reachable from the service's VPC; S3 permissions are needed at startup because the demo seed writes notes and sample files there. A seed failure prevents startup, so inspect CloudWatch if /health never becomes ready.

Bedrock, CloudShell and CodeBuild were blocked in the earlier account audit. This workflow avoids the AWS image-build blockers. It cannot lift an AWS account restriction on running ECS. Gemini still requires a working key and available model; AI configuration status alone is not a successful inference test. EMAIL_PROVIDER=log records reminder attempts and sends no email.

## Verify and demonstrate

1. Open /health and /api/auth/config; expect status ok and demo_enabled=true.
2. Open / and choose **Open student demo**. No credentials or registration.
3. Today → Subjects → Compiler Design → syllabus, notes and past questions.
4. Library → upload a small UTF-8 text file; wait for Ready, open the file (private S3 presigned URL).
5. Exams → Exam Rescue → choose a time budget → start a Study Desk session; edit notes and reload to show persistence in RDS.
6. Ask the tutor a question and check /api/ai/status after a real answer. AI should identify Gemini while Bedrock remains blocked.
7. Sign out → **Open teacher demo** → assignments and grading.
8. Check CloudWatch logs. Report the HTTPS URL, exact image tag and verification results.

The shared demo is intentionally public and uses synthetic records. Do not upload private university/student data to it.
