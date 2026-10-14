# PrepLoop: operations guide

Local development, first deploy, custom domain, and CI/CD. See the [README](../README.md) for the overview and [SPEC.md](SPEC.md) for the original spec.

---

## Local dev setup

Needs Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Create your local settings in the repo root (gitignored) and fill in the placeholders. It lives outside `backend/` so `sam build` never packages it.

```bash
cp .env.example .env
```

Sign-in needs a Google OAuth Client ID even locally (see "Google Cloud setup" below). For local dev, add **both** `http://localhost` and `http://localhost:8000` as Authorized JavaScript origins.

Run the app (from the repo root):

```bash
set -a; source .env; set +a
cd backend && uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 (port 8000 matches the Google OAuth origin). Health check: http://localhost:8000/api/health

Env vars used locally:

| Var | What it does |
|---|---|
| `LOCAL_MOCK_DB=1` | In-memory DynamoDB (moto), no AWS needed. Data is wiped on every restart or reload. To use the real table instead, remove it and set `TABLE_NAME` plus your AWS profile/region. |
| `GOOGLE_CLIENT_ID` | OAuth Client ID (public) |
| `ALLOWED_EMAIL` | The only Google account allowed in |
| `JWT_SECRET` | Local session signing key. In AWS the key comes from SSM via `JWT_SECRET_PARAM` instead. |
| `COOKIE_SECURE=false` | Local http only, so Safari keeps the cookie. Never set in AWS. |
| `FEEDBACK_MODEL_ID` | Bedrock model or inference profile ID, e.g. `us.amazon.nova-lite-v1:0` |
| `BEDROCK_REGION` | Region for Bedrock calls |
| `AWS_PROFILE` | Optional. Needed only for real AI feedback locally. With `LOCAL_MOCK_DB=1`, only Bedrock calls go to AWS; the table stays in-memory. |

Run tests (from `backend/`):

```bash
pytest -q
```

`sam local start-api` doesn't emulate Lambda Function URLs, so use uvicorn for local work.

---

## Google Cloud setup (manual, before deploying)

1. Create a GCP project (or reuse one). No billing needed.
2. Go to Google Auth Platform (OAuth consent screen):
   - User type: **External**
   - Fill in app name and my email
   - Leave publishing status as **Testing**
   - Add my own email as a **test user**
3. Go to Credentials, create an **OAuth client ID**, type **Web application**
4. Add **Authorized JavaScript origins** (exact match, no wildcards, no trailing slash):
   - `http://localhost:8000` for local dev
   - The Lambda Function URL (only known after the first deploy, so add it then)
   - `https://prep.joemakes.ca` once phase 2 is done
5. Leave redirect URIs empty (not needed for this flow)
6. Copy the **Client ID** and pass it to SAM as the `GoogleClientId` parameter

Changes to origins can take a few minutes to apply. In Testing mode only listed test users can sign in, which is fine since the backend also checks my email.

---

## AWS setup

### Prerequisites
- AWS account, AWS CLI configured (`aws configure` or SSO)
- SAM CLI installed
- Python 3.12
- Bedrock access for the chosen model in the console (Bedrock, Model access). Nova models are usually available without a request form, but confirm in the console. Claude may need a one-time use case form when I switch later.
- Pick a region where the chosen model (or its cross-region inference profile) is available, and pass the exact ID as a parameter

### SAM template should include
- `AWS::Serverless::Function` (Python 3.12, 512 MB, 30 to 60 s timeout since Bedrock can be slow)
  - `FunctionUrlConfig` with `AuthType: NONE` (the app handles its own auth)
  - Environment variables: table name, model ID, Bedrock region, Google client ID, allowed email, JWT secret parameter name
- `AWS::DynamoDB::Table` (on-demand)
- IAM permissions scoped to:
  - DynamoDB read/write on this one table
  - `bedrock:InvokeModel` on the chosen model / inference profile. Note: cross-region inference profiles need access to the underlying foundation model ARNs in each region the profile covers, so include those.
  - Read the specific SSM parameter for the JWT key
- Parameters: `FeedbackModelId`, `BedrockRegion`, `GoogleClientId`, `AllowedEmail`, `JwtSecretParam`
- Outputs: Function URL

### Secrets (create manually before first deploy)
- JWT signing key as a SecureString SSM parameter (long random string). Never commit it.

### Deploy
```bash
sam build
sam deploy --guided     # first time
sam deploy              # after that
```

After the first deploy: copy the Function URL, add it to the Google OAuth client's authorized JavaScript origins, then test sign-in.

### Deploy step by step (first time)

Replace `dev` with your AWS CLI profile and `us-east-1` with your region. Stack, SSM parameter, and Bedrock region should all be the same region.

1. Create the JWT signing key in SSM (once). The value is generated on the fly and never printed or saved:

   ```bash
   aws ssm put-parameter --profile dev --region us-east-1 --name /preploop/jwt-secret --type SecureString --value "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
   ```

2. Build (from the repo root):

   ```bash
   sam build
   ```

3. Deploy with prompts:

   ```bash
   sam deploy --guided --profile dev
   ```

   Answers:

   | Prompt | Answer |
   |---|---|
   | Stack Name | `preploop` |
   | AWS Region | `us-east-1` |
   | Parameter FeedbackModelId | Enter (keeps `us.amazon.nova-lite-v1:0`) |
   | Parameter BedrockRegion | Enter (keeps `us-east-1`) |
   | Parameter GoogleClientId | your Client ID (`...apps.googleusercontent.com`) |
   | Parameter AllowedEmail | your Google email |
   | Parameter JwtSecretParam | Enter (keeps `/preploop/jwt-secret`) |
   | Confirm changes before deploy | `y` |
   | Allow SAM CLI IAM role creation | `y` |
   | Disable rollback | `n` |
   | AppFunction Function Url has no authentication. Is this okay? | `y` (the app checks the Google sign-in itself) |
   | Save arguments to configuration file | `y` |
   | SAM configuration file / environment | Enter, Enter |

   Then type `y` at "Deploy this changeset?". Your answers go to `samconfig.toml` (gitignored), so later deploys are just `sam build && sam deploy`.

4. Copy `FunctionUrl` from the outputs. In Google Auth Platform > Clients > your client, add it to **Authorized JavaScript origins without the trailing slash**, e.g. `https://abc123.lambda-url.us-east-1.on.aws`. Wait a few minutes.

5. Check it:

   ```bash
   curl -s https://YOUR-FUNCTION-URL/api/health
   ```

   Then open the URL and sign in.

6. Optional sample questions (`TableName` is in the outputs):

   ```bash
   AWS_PROFILE=dev AWS_REGION=us-east-1 .venv/bin/python scripts/seed_sample_data.py YOUR-TABLE-NAME
   ```

Logs if something breaks:

```bash
sam logs --stack-name preploop --name AppFunction --profile dev --tail
```

Or in the console: CloudWatch > Log groups > `/aws/lambda/preploop-app`.

### Tear down
```bash
sam delete
```

This deletes the table too, so export your data first (Import / Export tab). The SSM parameter isn't part of the stack; delete it separately if you want.

---

## CI/CD (GitHub Actions)

`.github/workflows/ci-cd.yml`:
- **Every push and pull request:** install deps, run `pytest`, run `sam validate --lint`. No AWS access needed (tests use moto and a fake Bedrock).
- **Push to `main` (after tests pass):** `sam build` + `sam deploy` to the `preploop` stack, then a health check on the live URL. Deploys never overlap. The **Run workflow** button on the Actions tab redeploys `main` by hand.

AWS access uses **OIDC**: GitHub proves the job is from this repo's `main` branch and AWS returns short-lived credentials. No AWS keys are stored in GitHub. The deploy role (`infra/github-deploy-role.yaml`) trusts only `repo:TianweiZhou@43148828/preploop@1417624262:ref:refs/heads/main` (GitHub's immutable subject format: owner and repo IDs, so a renamed or re-created repo with the same name can't use it), has `PowerUserAccess`, and can only manage IAM roles named `preploop-*` (attaching nothing but the basic Lambda logging policy). It's named `github-deploy-preploop` so it can't edit itself.

### One-time setup

1. Create (or update) the deploy role. Pass `GitHubRepo` explicitly: on an existing stack, `cloudformation deploy` keeps old parameter values and ignores new template defaults. The account already has GitHub's OIDC provider, so `CreateOidcProvider` stays `false` (set it to `true` in an account that doesn't):

   ```bash
   aws cloudformation deploy --profile dev --region us-east-1 --stack-name github-deploy-preploop --template-file infra/github-deploy-role.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides GitHubRepo=TianweiZhou@43148828/preploop@1417624262
   ```

2. Get the role ARN:

   ```bash
   aws cloudformation describe-stacks --profile dev --region us-east-1 --stack-name github-deploy-preploop --query "Stacks[0].Outputs[0].OutputValue" --output text
   ```

3. In GitHub: repo > Settings > Secrets and variables > Actions. The repo is public, so personal values are **secrets** (masked in logs).

   | Type | Name | Value |
   |---|---|---|
   | Secret | `AWS_DEPLOY_ROLE_ARN` | ARN from step 2 |
   | Secret | `GOOGLE_CLIENT_ID` | Google OAuth Client ID |
   | Secret | `ALLOWED_EMAIL` | your Google email |
   | Secret | `HOSTED_ZONE_ID` | Route 53 zone ID for the domain |
   | Variable | `DOMAIN_NAME` | `prep.joemakes.ca` |
   | Variable (optional) | `FEEDBACK_MODEL_ID` | defaults to `us.amazon.nova-lite-v1:0` |
   | Variable (optional) | `RESERVED_CONCURRENCY` | defaults to `0` |

From then on, `git push` to `main` is the deploy. Changing a setting (e.g. switching to Claude) means changing the GitHub variable and clicking **Run workflow**, not `sam deploy --guided`, otherwise the next push would set it back.

---

## Phase 2: custom domain (`prep.joemakes.ca`)

Do this only after phase 1 works on the Function URL.

- Domain `joemakes.ca` is registered on Namecheap
- Subdomain: `prep.joemakes.ca`
- Add a CloudFront distribution in front of the Lambda Function URL
- Request an ACM certificate for `prep.joemakes.ca` **in `us-east-1`** (required for CloudFront), validated through DNS
- Point `prep.joemakes.ca` at the CloudFront domain with a CNAME (or alias record if DNS is on Route 53)
- DNS option A: keep DNS on Namecheap and add the two CNAME records manually (ACM validation and the subdomain). Simplest, no extra cost.
- DNS option B: move DNS to Route 53 (about $0.50/month) and manage records in the SAM template
- Start with option A unless there's a good reason not to
- Add `https://prep.joemakes.ca` to the Google OAuth authorized JavaScript origins
- Walk me through each manual DNS record step by step

**Decision: option B (Route 53).** `joemakes.ca` was brand new with nothing else on it, so moving its DNS cost nothing, and Route 53 lets the template create the certificate validation record and the `prep` alias automatically. The hosted zone is created once by hand, outside the app stack, so `sam delete` never removes it (which would change the nameservers).

What the template adds when `DomainName` is set:
- ACM certificate for the domain, validated automatically through Route 53
- CloudFront in front of the Function URL: no caching (every response is per user), all methods, cookies, and query strings passed through, the `Host` header not forwarded (Function URLs reject it), 60 s origin timeout for slow Bedrock calls, AWS managed security headers (HSTS etc.)
- Route 53 `A` and `AAAA` alias records pointing the domain at CloudFront

### Custom domain step by step

1. Create the hosted zone (once):

   ```bash
   aws route53 create-hosted-zone --profile dev --name joemakes.ca --caller-reference "joemakes-$(date +%s)" --query '[HostedZone.Id, DelegationSet.NameServers]'
   ```

   Note the zone ID (the part after `/hostedzone/`, like `Z0123456789ABC`) and the 4 nameservers.

2. In Namecheap: Domain List > `joemakes.ca` > Manage > Nameservers > **Custom DNS**. Enter the 4 AWS nameservers (without the trailing dot) and save.

3. Wait until the switch is visible (usually minutes, can take a few hours). This must show the AWS nameservers before you deploy, or certificate validation will hang:

   ```bash
   dig NS joemakes.ca +short
   ```

4. Deploy with the two new parameters. `--guided` re-asks every parameter with your saved answers as defaults, so press Enter for the old ones and fill in:
   - `DomainName`: `prep.joemakes.ca`
   - `HostedZoneId`: the zone ID from step 1
   - `ReservedConcurrency`: Enter (keeps `0`, see below)

   ```bash
   sam build && sam deploy --guided --profile dev
   ```

   The certificate and CloudFront take about 5 to 15 minutes.

5. In Google Auth Platform > Clients > your client, add `https://prep.joemakes.ca` to **Authorized JavaScript origins**. Keep the Function URL origin too.

6. Check it, then open https://prep.joemakes.ca and sign in:

   ```bash
   curl -s https://prep.joemakes.ca/api/health
   ```

The Function URL keeps working too. That's fine: every data route needs the signed session cookie either way.

### Concurrency cap

`ReservedConcurrency` caps how many copies of the function run at once, which caps worst-case cost if someone floods the URL. New AWS accounts have an account-wide limit of 10, and AWS requires 10 to stay unreserved, so the cap can't be set yet (the low account limit already acts as a cap). Once the account limit is raised (it grows with usage, or request 1000 in Service Quotas > AWS Lambda > Concurrent executions), redeploy with `ReservedConcurrency=10`.

---

## Switching to Claude later

1. Enable Claude model access in the Bedrock console
2. Update the `FeedbackModelId` parameter to the Claude model or inference profile ID (with CI/CD: the `FEEDBACK_MODEL_ID` GitHub variable, then **Run workflow**)
3. Update the IAM policy resource if needed (the template should derive it from the parameter)
4. `sam deploy`

No code changes should be needed because the app uses the Converse API.
