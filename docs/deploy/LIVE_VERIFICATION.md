# AWS demonstration verification — 29 October 2026

Public service: https://un-77dd2c16f6e94ab593853d98dc3c3504.ecs.ap-south-1.on.aws

Deployed image: `ghcr.io/kauziee-hub/unitask:072282dc88fba17bb22bfc107393a667d28c746a`.

## Verified against the actual AWS service

- HTTPS `/health`: version 3.0.0, status ok.
- Signup-free demo enabled; student and teacher sessions both work.
- Website HTML and client-side deep links are served.
- Dashboard, subjects, notes, exams and insights respond successfully.
- A new text file was uploaded, processed, downloaded through a private S3 signed URL and checked byte-for-byte. The test upload was then removed.
- Study Desk notes and checklist survived a read from a fresh HTTP client; the test session was completed.
- A real Gemini tutor request returned an answer using `gemini-3.5-flash`; the conversation persisted in the database.

Machine-readable evidence is in [live-verification.json](live-verification.json). No credentials, bearer tokens or signed file URLs are recorded. These checks verify the deployed API and data paths; interactive browser rendering of the AWS site remains unverified on this network.

## Remaining demonstration-laptop issue: DNS

This laptop's configured Wi-Fi DNS resolver (`10.223.215.246`) returns NXDOMAIN for the service hostname. Google public DNS and a direct query to Cloudflare `1.1.1.1` both resolve it to AWS addresses. Requests to a published address with the original HTTPS hostname and normal certificate validation succeed. The application is reachable; the laptop's default resolver is the remaining access problem.

An attempted local DNS-cache flush reported that administrator elevation is required. No network settings were changed.

Before the presentation, open the public URL using mobile data/a different network, or configure a working DNS resolver (for example Cloudflare `1.1.1.1`) on the demonstration browser/network. Confirm the normal URL opens, then select **Open student demo**.

## Reproduce the checks

```powershell
.\.venv\Scripts\python.exe scripts/verify_deployment.py https://un-77dd2c16f6e94ab593853d98dc3c3504.ecs.ap-south-1.on.aws --report verification.json
```

If the local resolver still fails, obtain a fresh A record from public DNS and supply it using `--resolve-address`. This option retains TLS hostname/certificate validation. Do not treat a historical IP address as permanent.

The verifier writes synthetic demonstration records and makes one real AI request. Reminder emails remain log-only, and the deployed AI provider is Gemini. Bedrock is outside this verified flow.
