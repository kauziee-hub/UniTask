# UniTask AI — Amazon S3 timetable demo

This guide documents the S3 timetable-storage demo. Local file storage remains the application default when `STORAGE_PROVIDER` is unset; the ignored local `backend/.env` selects the approved demo bucket. The bucket setup and one test-image upload/retrieval have been explicitly approved and completed. Do not create other AWS resources or perform additional test uploads without approval.

## Verified preflight

- AWS CLI profile `unitask-demo` resolved to `ap-south-1`.
- `sts get-caller-identity` returned `arn:aws:iam::687159379583:user/unitask-demo-s3`.
- A read-only `HeadBucket` request returned 404 for `unitask-ai-timetable-demo-2026-1931`. The name appeared unused at probe time, but this does not reserve it or guarantee it is globally available; another account could claim it before creation.
- After the owner approved setup and the IAM policy was updated, bucket creation succeeded. The ownership-controls, public-access-block, and default-encryption configuration calls also succeeded.
- Read-back verification succeeded: ownership is `BucketOwnerEnforced`; all four Block Public Access settings are `true`; and default encryption is `AES256`.
- `get-bucket-policy-status` and `get-bucket-acl` returned `AccessDenied`, so those individual policy/ACL documents were not inspected. The verified full Block Public Access configuration prevents public ACL access and blocks/restricts public bucket policies; the bucket is private from public access.
- The local backend `.env` selects `STORAGE_PROVIDER=s3` with the intended bucket, region, and AWS profile. The API accepted one approved 69-byte PNG upload, and retrieval through its presigned GET URL returned HTTP 200 with identical bytes.
- The first retrieval attempt exposed a global-endpoint presigning issue. The adapter now uses regional virtual-hosted S3 URLs, and a mocked regression test checks the regional hostname.
- The approved test object remains under the bucket's `timetables/` prefix. No other object was uploaded and no other AWS resource was created. Do not delete the test object without approval.
- Setup, verification, failed retrieval attempts, one PUT, and the successful GET generated S3 requests. Further uploads, previews, storage, and transfer may incur charges; the exact cost depends on current regional pricing and the account offer. The account credits and plan were supplied by the owner and do not guarantee zero cost; review AWS billing and current S3 pricing.

## AWS setup

The AWS CLI profile must use the dedicated IAM user `unitask-demo-s3`, in `ap-south-1`. Never use root credentials or put access keys in the application environment, source code, browser, or chat. The app uses the AWS SDK profile chain (`AWS_PROFILE`) on the local backend.

Bucket creation and all three configuration requests have succeeded, and their settings have been read back and verified. Do not rerun the create or configuration commands for this existing bucket. The separate policy-status and ACL reads were denied; the verified four Block Public Access settings block public ACL access and block/restrict public policies.

```powershell
$aws = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe"
& $aws s3api create-bucket `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --region ap-south-1 `
  --create-bucket-configuration LocationConstraint=ap-south-1 `
  --profile unitask-demo
```

Immediately configure ownership, disable all public access, and enable S3-managed encryption:

```powershell
& $aws s3api put-bucket-ownership-controls `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]' `
  --profile unitask-demo

& $aws s3api put-public-access-block `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true' `
  --profile unitask-demo

& $aws s3api put-bucket-encryption `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --server-side-encryption-configuration 'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]' `
  --profile unitask-demo
```

These are S3-only commands retained as a setup reference; they have already been run successfully. Do not add a bucket policy, public ACL, website hosting, or any other AWS service.

## Local environment

The backend reads `backend/.env` at startup. The prepared local file selects S3 and contains the supported settings (`S3_BUCKET`, `AWS_REGION`, and `AWS_PROFILE`) without credentials. The application-wide default remains local when `STORAGE_PROVIDER` is unset.

For local fallback, change this line in `backend/.env`:

```dotenv
STORAGE_PROVIDER=local
```

The configured S3 bucket, region, and profile are already present. Install the optional Boto3 dependency if needed:

```powershell
Set-Location 'C:\Users\Rithish\Desktop\UniTask-AI\backend'
.\.venv\Scripts\Activate.ps1
pip install -r requirements-aws.txt
```

Do not set credentials in `.env`; the AWS SDK reads them from the local `unitask-demo` profile. Keep the backend bound to localhost; the upload API has no authentication and is for local demonstration only.

## Start the app

In a PowerShell terminal:

```powershell
Set-Location 'C:\Users\Rithish\Desktop\UniTask-AI\backend'
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

In a second terminal:

```powershell
Set-Location 'C:\Users\Rithish\Desktop\UniTask-AI\frontend'
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). The frontend proxies timetable API requests to the local FastAPI service at `http://127.0.0.1:8000`.

## Upload a timetable

1. Confirm the bucket's public-access protections in AWS Console and ensure the IAM profile has `s3:PutObject` and `s3:GetObject` access scoped to `arn:aws:s3:::unitask-ai-timetable-demo-2026-1931/timetables/*`.
2. Confirm `backend/.env` has `STORAGE_PROVIDER=s3`, then restart the backend.
3. In the app's timetable workspace, choose a JPEG, PNG, or WebP image no larger than 5 MB and upload it.
4. The API validates the image, writes a uniquely named object under `timetables/`, and saves upload metadata in SQLite.
5. The UI should show the image returned through a short-lived presigned GET URL. This is not OCR; the image is stored and previewed only.

## Verify in AWS

In AWS Console, open **S3 → Buckets → `unitask-ai-timetable-demo-2026-1931`** in `ap-south-1`, then inspect the `timetables/` prefix. Confirm that the bucket's **Permissions → Block public access** settings remain fully enabled. Do not make the object public.

The API's upload response includes `file_url`, a presigned URL that permits retrieval for five minutes. The app preview exercises that URL. To retrieve it separately, copy the `file_url` from the local API response and use it promptly:

```powershell
Invoke-WebRequest -Uri '<presigned-file_url>' -OutFile '.\timetable-preview'
```

Treat the full URL as a temporary bearer token: do not post it publicly or commit it. One real S3 upload and retrieval have succeeded through the API integration; further uploads are not needed to establish the demo.

## Cleanup

Only after explicit approval to remove the demo data, and only if this bucket contains no data that must be kept:

```powershell
$aws = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe"
& $aws s3 rm s3://unitask-ai-timetable-demo-2026-1931/timetables/ `
  --recursive --profile unitask-demo
& $aws s3api list-objects-v2 `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --profile unitask-demo
```

After confirming the bucket is empty, delete it:

```powershell
& $aws s3api delete-bucket `
  --bucket unitask-ai-timetable-demo-2026-1931 `
  --region ap-south-1 `
  --profile unitask-demo
```

Then restore `STORAGE_PROVIDER=local` in `backend/.env` and restart the backend. SQLite upload metadata is not removed by S3 cleanup and may refer to objects that no longer exist.

## Presentation explanation

“The backend stores timetable images in a private Amazon S3 bucket. Public access is blocked; the app displays an image using a presigned retrieval link that expires after five minutes. The demo supports storage and preview only—there is no OCR or timetable extraction. Local storage remains the default when S3 is disabled.”
