# PrepLoop

A small personal web app to store interview questions with my own answers, practice them, and get AI feedback using Amazon Bedrock. Built to be used for a couple of months, so the goal is **simple, cheap, and fast to deploy**. Also a portfolio piece.

Live at: `https://prep.joemakes.ca` (domain registered on Namecheap)

> **Note for Claude Code:** This README is the spec. Build the whole project from it. Keep things simple, avoid over-engineering, and prefer fewer files and fewer dependencies. Ask me before adding anything not described here. After building, walk me through the deploy steps.

---

## Goals

- Add interview questions plus my answers (technical and behavioral)
- Practice mode that hides the answer until I reveal it
- AI feedback on my answers via Amazon Bedrock (starting with a cheap Amazon Nova model, switching to Claude later by changing one parameter)
- Runs on AWS serverless, near zero cost when idle
- Deploy with `sam build && sam deploy`
- Single user (me), signed in with Google

## Non-goals

- No multi-user accounts or sign-up
- No React or build step for the frontend
- No RDS or any always-on infrastructure
- No Cognito (direct Google sign-in is enough)
- No CI/CD at first (manual deploy is fine, can add GitHub Actions later)

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Mangum (ASGI adapter for Lambda) |
| Compute | AWS Lambda with a Function URL |
| Database | DynamoDB (on-demand billing) |
| AI | Amazon Bedrock, **Converse API** (model-agnostic). Default model: Amazon Nova Lite. Later: Claude |
| Auth | Google Identity Services ("Sign in with Google") + `google-auth` ID token verification + own session cookie |
| Frontend | Plain HTML, CSS, and vanilla JS, served by the same Lambda |
| IaC | AWS SAM (`template.yaml`) |
| Secrets | SSM Parameter Store (SecureString) for the JWT signing key |
| Custom domain | CloudFront + ACM certificate + DNS record (phase 2) |

---

## Repo layout

```
preploop/
  README.md
  template.yaml            # SAM template
  samconfig.toml           # created by `sam deploy --guided`
  backend/
    app/
      main.py              # FastAPI app + Mangum handler
      auth.py              # Google token verification, session cookie, auth dependency
      db.py                # DynamoDB access
      models.py            # Pydantic models
      feedback.py          # Bedrock Converse calls + prompts + JSON parsing
      routes/
        questions.py
        practice.py
        feedback.py
        io.py              # import / export
      static/
        index.html
        app.js
        styles.css
    requirements.txt       # runtime deps (deployed)
    requirements-dev.txt   # local dev + test deps
    pytest.ini
    tests/
  scripts/
    seed_sample_data.py    # optional sample questions
  .gitignore
```

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

## Features

### 1. Question library
- Create, edit, delete questions
- Fields:
  - `type`: `technical` or `behavioral`
  - `question` (text)
  - `answer` (text, my own answer)
  - `star` (optional, behavioral only): `situation`, `task`, `action`, `result`
  - `tags` (list of strings, e.g. `RAG`, `AWS`, `leadership`)
  - `confidence` (1 to 5)
  - `notes` (optional)
- List view with:
  - Filter by type, tag, confidence
  - Search by text
  - Sort by confidence, last practiced, created date

### 2. Practice mode
- Pick a filter (type, tag) and start a session
- A session goes through each matching question once, with a progress bar and answered / skipped / left counts, then a "session complete" summary
- Shows the question only
- Button to reveal my saved answer
- After reveal, I rate my confidence 1 to 5, which updates the question
- Question selection is weighted so low confidence and not recently practiced questions show up more
- Updates `lastPracticed` and `timesPracticed`
- Optional: a text box to type a fresh answer and get AI feedback on it before saving

### 3. AI feedback (Bedrock)
- "Get feedback" button on any question with an answer, and in practice mode
- Feedback is stored on the question (last 3 reviews). If the type, question, and answer text are unchanged and the model is the same, the stored review is returned without calling Bedrock. A "Get fresh feedback" link forces a new call
- Library cards and practice show the latest AI scores for the current answer
- Backend sends the question, type, tags, and the answer to the model through the **Bedrock Converse API**
- Use Converse (not the model-specific InvokeModel formats) so switching from Nova to Claude later is only a config change, with no code change
- Model ID comes from a SAM parameter / env var (`FEEDBACK_MODEL_ID`), never hardcoded
- **Default model: Amazon Nova Lite** (or Nova Micro). Bedrock has no truly free models, but Nova is very cheap, so a few hundred feedback calls should cost cents. Check the Bedrock console for the exact model ID or cross-region inference profile ID available in the chosen region.
- Later I will switch to a Claude model by changing `FEEDBACK_MODEL_ID` and enabling Claude access in the Bedrock console. Prompts should stay model-agnostic so this just works.
- The model must return **JSON only**. Smaller models are less reliable at this, so:
  - Tell it clearly to output only JSON, no markdown fences, no preamble
  - Strip code fences if present, then parse and validate with Pydantic
  - If parsing fails, retry once with a stricter reminder, then return a readable error
- Expected shape:

```json
{
  "scores": { "clarity": 1-5, "structure": 1-5, "specificity": 1-5 },
  "strengths": ["..."],
  "gaps": ["..."],
  "suggested_answer": "...",
  "follow_up_questions": ["..."]
}
```

- Prompt behavior:
  - **Behavioral:** check STAR structure, flag missing measurable results, flag vague "we" instead of "I", keep the suggested answer spoken-length (about 1 to 2 minutes)
  - **Technical:** check accuracy and depth, flag errors or missing tradeoffs, suggest what a senior interviewer would expect
  - Be direct and honest, not flattering. Point out real weaknesses.
  - Suggested answer should keep my voice and stay concise, natural, and conversational. Avoid corporate buzzwords and avoid em dashes.
  - Keep the prompt short and simple so cheaper models follow it well
- Handle Bedrock errors cleanly (throttling, access denied, model not enabled) and show a readable message in the UI
- Show which model produced the feedback in the UI (small label), useful when I compare Nova and Claude later

### 4. Import / export
- Import from JSON or CSV (columns: `type, question, answer, tags, confidence`; tags separated by `;`)
- Export everything to JSON or CSV
- Import should skip exact duplicate questions

### 5. Auth (Google sign-in, single user)
Flow:
1. Frontend shows a login screen with the "Sign in with Google" button (Google Identity Services script, `https://accounts.google.com/gsi/client`)
2. Google returns an **ID token** (credential) in the browser
3. Frontend sends it to `POST /api/auth/google`
4. Backend verifies it with the `google-auth` library (`google.oauth2.id_token.verify_oauth2_token`), checking:
   - signature and expiry are valid
   - audience matches my `GOOGLE_CLIENT_ID`
   - `email_verified` is true
   - `email` exactly matches `ALLOWED_EMAIL` (my email, set as a SAM parameter)
5. If all pass, backend sets a signed session JWT in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie (expires in 7 days). Signing key comes from SSM.
6. Anyone else, including other valid Google accounts, gets `403`
7. All `/api/*` routes except `/api/auth/google`, `/api/logout`, and `/api/health` require a valid session cookie

Notes:
- No client secret and no redirect URIs are needed for this flow, only the Client ID (not a secret, fine to expose to the frontend via a small `/api/config` endpoint or injected into the page)
- No password and no login rate limiting needed

---

## Data model

One DynamoDB table, on-demand billing. The dataset is small (hundreds of items), so a full `Scan` plus filtering in Python is fine. Don't over-design the keys.

Table: `<stack name>-questions` (e.g. `preploop-questions`) instead of a fixed `InterviewPrepTable`, so a second stack never clashes. The Lambda function is `<stack name>-app`.
- Partition key: `pk` (string), e.g. `Q#<uuid>`

Item attributes:

```
pk, id, type, question, answer,
star { situation, task, action, result },
tags [string], confidence (int),
notes, lastPracticed (ISO string or null),
timesPracticed (int), createdAt, updatedAt
```

---

## API

All JSON, all under `/api`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Returns public config (Google Client ID), no auth |
| POST | `/api/auth/google` | Verify Google ID token, set session cookie |
| POST | `/api/logout` | Clear cookie |
| GET | `/api/me` | Returns signed-in email, used by the frontend to check session |
| GET | `/api/questions` | List, supports `type`, `tag`, `min_conf`, `max_conf`, `q` |
| POST | `/api/questions` | Create |
| GET | `/api/questions/{id}` | Get one |
| PUT | `/api/questions/{id}` | Update |
| DELETE | `/api/questions/{id}` | Delete |
| POST | `/api/practice/next` | Next weighted question. Body: `type`, `tag`, `seen` (ids already shown this session). Returns `{question, total, remaining}`, `question` is null when the session is done |
| POST | `/api/practice/{id}/rate` | Save confidence, update practice stats |
| POST | `/api/feedback` | Body: `question_id` (optional `answer` to review a fresh one) or raw `{question, type, answer}`, plus optional `force`. Returns AI feedback JSON, model ID, `created_at`, and `cached` |
| POST | `/api/import` | Upload JSON or CSV |
| GET | `/api/export?format=json\|csv` | Download all data |
| GET | `/api/health` | Health check, no auth |

---

## Frontend

Plain HTML, CSS, and vanilla JS, no framework, no build step.

- **Login screen:** just the Google button. After success, show the app.
- Three views in a simple tab layout:
  1. **Library:** table or card list with filters, search, add/edit form
  2. **Practice:** question card, reveal button, confidence buttons 1 to 5, optional "type my answer" box, feedback panel
  3. **Import / Export**

Design notes:
- Clean, minimal, works well on a laptop and on a phone
- Support dark mode with `prefers-color-scheme`
- Keyboard shortcuts in practice mode (space to reveal, 1 to 5 to rate) are a nice touch
- Show feedback scores as small bars and the lists as plain bullets
- Escape all user content before rendering to avoid XSS

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

## Switching to Claude later

1. Enable Claude model access in the Bedrock console
2. Update the `FeedbackModelId` parameter to the Claude model or inference profile ID (with CI/CD: the `FEEDBACK_MODEL_ID` GitHub variable, then **Run workflow**)
3. Update the IAM policy resource if needed (the template should derive it from the parameter)
4. `sam deploy`

No code changes should be needed because the app uses the Converse API.

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

## Security checklist

- No secrets in the repo, `.gitignore` covers `.aws-sam/`, `samconfig.toml` if it has sensitive values, `.env`
- Always verify the Google ID token on the backend. Never trust the frontend.
- Check audience, expiry, `email_verified`, and exact email match
- Cookie flags: `HttpOnly`, `Secure`, `SameSite=Strict`
- Least-privilege IAM
- Input validation with Pydantic, length limits on text fields
- Limit request body size for import
- Escape output in the frontend
- CORS not needed since the frontend is served from the same origin, so keep it off

---

## Testing

- A few pytest tests for: auth (valid token, wrong email, wrong audience, mocked Google verify), question CRUD (use `moto` for DynamoDB), practice weighting, feedback JSON parsing including messy model output (mock Bedrock)
- `sam local start-api` for quick local checks if useful
- Don't spend long on tests, just cover the core logic

---

## Build order

1. Scaffold the repo, FastAPI app, health route, Mangum handler
2. DynamoDB layer + question CRUD + tests
3. Google auth (token verification, cookie, dependency, login screen)
4. Frontend library view
5. Practice mode + weighting
6. Bedrock Converse feedback + prompts + JSON parsing + error handling
7. Import / export
8. SAM template, deploy, verify on the Function URL
9. Phase 2 custom domain

---

## Ideas for later (not now)

- Timed mock interview mode with a random question set
- Voice answers with transcription
- Progress chart over time
- GitHub Actions auto deploy
- Question packs seeded from common AI/ML engineer interview topics (RAG, evaluation, agents, system design on AWS)
- Side by side feedback comparison between models
