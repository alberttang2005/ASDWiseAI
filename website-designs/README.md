# ASDWise Haven

Anonymous caregiver screening with a Next.js interface and a Python API function in the same Vercel project. See [Vercel deployment](docs/DEPLOYMENT.md). No sign-in, accounts, database, or saved interview history. Deployment requires the environment secrets and domain setup described in that guide.

## Run locally

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r src/web/requirements.lock.txt
cd website-designs
npm ci
ASDWISE_ENV_FILE=/absolute/private/path/haven.env npm run pilot
```

Open http://localhost:3000. The launcher binds Next.js to port 3000 and Python to 8001 on loopback, using a private gateway secret. `ASDWISE_PYTHON` can override the Python executable. `npm run build` checks the frontend; after building, `ASDWISE_PRODUCTION=1 npm run pilot` runs that build.

## Server secrets

Use a private environment file outside the repository or deployment secrets:

```dotenv
OPENAI_API_KEY=your-project-key
THERAPIST_MODEL=gpt-5-nano
EVALUATOR_MODEL=gpt-5-mini
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
SPEECH_MODEL=gpt-4o-mini-tts
```

Never use a NEXT_PUBLIC variable for credentials. A missing key disables new conversations; there is no demo fallback. Changing credentials requires a server restart.

## Temporary processing only

Interviews, reports, and recordings are processed in memory. No database or session files are created. An anonymous HTTP-only session cookie isolates caregivers; it contains no interview content. The app does not store transcripts in browser storage.

An explicit end-session action clears the interview. The browser also attempts cleanup when leaving or refreshing; this is best-effort. Browser-carried, signed state expires after 30 minutes without updates. Vercel cold starts preserve progress because each request carries its own snapshot. Leaving or refreshing loses access to the current interview. Download the PDF before ending the session.

OpenAI processing/retention is separate from this app's non-persistence and must be reviewed for deployment. Do not enable body logging, transcript analytics, request capture, or persistent job queues. Old databases from earlier local versions are not read by this version; they are not automatically deleted.

## Workflow

- Onboarding, 16–30-month eligibility information, and processing consent.
- Canonical questions, AI clarification, caregiver-confirmed yes/no/unknown answers, and review.
- Typed answers or editable microphone transcription, optional AI speech, and typing fallback.
- Deterministic initial scoring; unresolved answers do not produce a final classification.
- Supplemental observations, evidence-linked report sections, and PDF downloads during the active session.
- Simulation requests are rejected. Fictional profiles and report fixtures exist only for testing.

## Remaining release requirements

Formal M-CHAT-R Follow-Up is not implemented; moderate initial results explicitly show it as pending. Confirm instrument wording and electronic-use permission, and complete qualified review of interpretations/recommendations. The supplied February 2013 DSM exemplar document is labeled as a draft; published criteria context is separately attributed. Screening does not establish diagnosis.

The Vercel adapter uses browser-carried state and request-local processing. Production uses HTTPS, server-only secrets, and redacted monitoring. See the deployment guide for stateless replay and per-instance admission limitations. Real-device microphone and accessibility checks remain required.

## Local runtime controls

The process limits below describe the original local runtime. On Vercel they apply per instance only; they are not distributed spend or admission limits. See the deployment guide.


Run one Next.js process and one Python worker. Each process enforces a global limit of 600 API requests and 20 new sessions per minute, independent of anonymous cookies. The gateway also caps active requests (including event streams and uploads) at 32, with a 200-second deadline. The backend additionally permits 120 requests per owner per minute; inactive owner entries expire and the table has a fixed capacity. Arbitrary client-supplied forwarding headers are not trusted as IP identities. For public hosting, apply per-client limits at a trusted reverse proxy as well: shared global limits bound resource use, but cannot guarantee fairness against a determined attacker. Multiple replicas require shared admission controls before scaling out.

All paid AI operations share a fail-closed concurrency limit and a finite usage allowance:

```dotenv
ASDWISE_AI_CONCURRENCY=4
ASDWISE_AI_BUDGET_UNITS=1000
```

These backend settings may be placed in the private environment file or Vercel environment settings. Defaults apply when omitted; zero budget disables paid operations. A guide response uses 1 unit, transcription 3, speech 2, and a report 20 (including its possible validation retry). Failed or cancelled calls still consume their reserved units. Capacity rejection returns 429; exhausted usage returns 503 without starting paid work. These are operation allowances, not dollar estimates or a persistent billing cap. They reset only when Python restarts. Configure provider-side spending controls separately, and do not automatically restart the service to replenish an exhausted allowance.

Sessions are limited to 2 MiB of serialized state and 300 turns. Context retains at most 50 superseded observations plus the five current fields; current evidence is preserved. Report and idempotency histories are capped at 10 and 200 entries. Session locks use 256 fixed stripes, so invalid IDs cannot grow a lock table. Old report snapshots remain self-contained when context history is trimmed.

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_haven.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_security.py' -v
cd website-designs && node --test scripts/security.test.mjs
```

Tests use fictional caregiver data and fake providers. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for live-provider verification and [the plan](docs/IMPLEMENTATION_PLAN.md) for remaining work.

## Caregiver-perspective improvements

The guide uses GPT-5 nano with minimal reasoning; report analysis defaults to GPT-5 mini with low reasoning. Models remain configurable. Reports have a 120-second application deadline; SDK retries are disabled, and at most one evidence-validation repair fits inside that same deadline. A timeout preserves answers for a deliberate retry. Model overrides may change latency and interpretation quality and should be re-tested.

Optional onboarding context records setting, frequency, and familiarity. Additional context can retain another caregiver's differing observations, attributed as reported rather than assumed firsthand. Reports show that scope, lead with everyday observations and next steps, and keep technical criteria expandable. Exact quotes and page references are inserted from existing caregiver records and approved criterion mappings; the model selects evidence IDs. Unknown IDs, unsupported concerns, and reused concern evidence remain rejected.

Provider metrics contain only operation, duration and token counts; no transcripts or credentials are logged.
