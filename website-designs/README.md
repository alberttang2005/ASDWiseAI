# ASDWise Haven — local research pilot

Haven is now connected to a Python API for caregiver interviews, explicit answer confirmation, resumable encrypted sessions, detailed evidence-linked reports, PDF downloads, and optional voice input/output.

## Start locally

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r src/web/requirements.lock.txt
cd website-designs
npm ci
npm run pilot
```

Open http://localhost:3000. The launcher starts Next.js on loopback port 3000 and Python on loopback port 8001 with an ephemeral private gateway secret. It stops both when interrupted. Stop any older Next.js preview for this directory first.

For the environment used during implementation, the Python dependencies are installed in `/private/tmp/asdwise-venv`. You can start with:

```bash
ASDWISE_PYTHON=/private/tmp/asdwise-venv/bin/python npm run pilot
```

`npm run dev` alone starts only the UI; use `npm run pilot` for the complete app. `npm run build` validates the Next.js production build. After building, `ASDWISE_PRODUCTION=1 npm run pilot` runs the built app locally.

## Server-side API configuration

The app starts without an API key in **synthetic demo mode**. The low/moderate/high profiles are fictional stored observations; their report template is explicitly not an AI clinical assessment. This mode needs no paid API calls.

For live AI conversations and audio, create an environment file **outside this Google Drive-synced repository**, readable only by your user. Set:

```dotenv
OPENAI_API_KEY=your-project-key
THERAPIST_MODEL=gpt-5-nano
EVALUATOR_MODEL=gpt-5-nano
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
SPEECH_MODEL=gpt-4o-mini-tts
ASDWISE_DATA_DIR=/absolute/non-synced/path/to/ASDWise-data
```

Then launch (from this directory):

```bash
ASDWISE_ENV_FILE=/absolute/non-synced/path/to/haven.env npm run pilot
```

The Python process loads that explicit file; repository `.env` files are not automatically loaded by the new web API. Restart the pilot after configuring credentials. Never use `NEXT_PUBLIC_` variables for keys, put keys in client files, or paste credentials into chat. Model access and billing must be enabled in your API project. Live provider behavior has not been tested without credentials.

## Implemented workflow

- Onboarding with child name/nickname, 16–30-month scope, relationship, and a processing/storage notice.
- Exact project question text, caregiver narrative, AI clarification, explicit yes/no/unknown confirmation, optional quick answers, transcript review.
- Pause/resume/reset; persisted session recovery; separate step-by-step or automatic synthetic demos.
- Unknown/missing answers remain incomplete; deterministic reverse scoring for items 2/5/12; all 20 initial answers required for a final initial score.
- Formal Follow-Up is explicitly **pending** for moderate initial scores. The formal Follow-Up instrument itself is not implemented, and conversational clarification is not presented as a substitute.
- Optional supplemental onset, impact, routines, and interest observations.
- Push-to-talk recording (90-second / 8 MB limits), editable transcription before submission, read-aloud and stop/mute, cancellation and typing fallback. Audio requires provider access and a browser that supports microphone recording; HTTPS is required outside localhost.
- A1–A3/B1–B4 report sections, exact caregiver quotes, turn references, source pages, missing context, strengths, summary, and deterministic next-step guidance.
- Source/quote validation, safe report errors, background report jobs and server-sent status updates, immutable report versions, stale report detection after edits, PDF downloads.
- Seven-day inactive-session retention, deletion, encrypted local records, HTTP-only owner cookie, same-origin mutation protection, gateway authentication, request/upload limits. A session can be resumed only from its owning browser cookie; clearing cookies loses access.

## Grounding and limits

`src/web/reference.json` contains a page-indexed extraction and SHA-256 provenance of the supplied Laura Carpenter February 2013 guidelines. It is identified as a **pre-publication exemplar reference**. A separately attributed CDC published-criteria summary supplies the current A–E context; the app does not diagnose or assign severity.

The LLM never calculates scores. It receives reference content and interview data as data, returns a validated schema, and cannot supply arbitrary HTML. Unverifiable quotes, invalid reference pages, duplicate concern evidence, or invalid criteria cause generation to fail instead of saving an unverified report. B2/B3 concern evidence must come from the corresponding supplemental observations. These checks do not establish clinical validity; qualified review is still needed before real-world use.

Live guide output is delivered after its structured response is validated; the app streams session/report state rather than displaying partial unvalidated model JSON. No transcript is stored in browser localStorage. Audio is processed in memory and not retained by this app; provider-side processing/retention is separate.

Default pilot data lives in `/private/tmp/asdwise-haven-data` and may be removed sooner by the operating system. For durable local use, set an external `ASDWISE_DATA_DIR`. The storage directory and encryption key are protected by user-only filesystem permissions; records are encrypted using Fernet. Back up or delete the key and database together.

## Deployment scope

This deliverable is a **single-user local research pilot**. Both services bind to loopback. Do not expose this configuration as a public clinical service. For a private hosted pilot, terminate HTTPS at a trusted proxy, restrict Python to the gateway, configure persistent private storage, and review access/retention and instrument permissions. An optional `ASDWISE_ACCESS_PASSWORD` environment variable (provided to Next.js, username `caregiver`) adds shared HTTP Basic protection to API routes; it is not a multi-user account system. Formal clinical review, real-device microphone testing, and live provider validation remain release gates.

## Tests

From repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_haven.py' -v
```

Tests use a fake provider and synthetic data. They cover scoring boundaries, unresolved answers, ownership, confirmation, pause/resume, retry idempotency, stale revisions, failure recovery, synthetic profiles, report evidence, PDF generation, audio endpoint behavior, and encryption/reload. Browser checks cover the integrated demo, review/report navigation, and mobile layout. Microphone permissions/audio quality and real API outputs require a configured account and actual hardware testing.

Architecture details and original acceptance criteria: `docs/IMPLEMENTATION_PLAN.md`.
