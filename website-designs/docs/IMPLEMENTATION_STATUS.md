# Implementation status — updated September 16, 2026

Product target: a real caregiver-facing screening application. The delivered work below describes the local pilot baseline; demo functionality is scheduled for removal from the production app. See IMPLEMENTATION_PLAN.md for the revised release sequence.

## Delivered

- Haven onboarding, conversational UI, typed and voice response paths, explicit answer confirmation, clarification without advancing, quick answers, and complete transcript review.
- Python FastAPI service with session revision checks, retry idempotency, encrypted SQLite storage outside the repository, per-browser ownership, seven-day expiry, and deletion.
- Deterministic scoring reused from the Python application, hardened against unresolved inputs. The legacy therapist now only extracts unambiguous standalone answers automatically; narrative interpretation in the web app requires caregiver confirmation.
- Separate synthetic profiles, manual/automatic stepping, pause/resume/reset, and refresh recovery.
- Supplemental onset, daily impact, routines, and interests observations.
- Structured OpenAI therapist/evaluator adapters; separately configurable text, transcription, and speech models. Explicit server-only environment loading.
- Page-indexed extraction of the supplied DSM exemplar document, author/date/checksum provenance, a separately identified CDC published-criteria summary, quote validation, criterion/reference validation, and conservative evidence requirements.
- Detailed report UI and PDF download from shared report data, immutable revisions, stale-report detection, and background report generation with streamed status updates.
- Same-origin Next.js gateway, hidden private gateway secret, upload/request limits, HTTP-only owner cookies, loopback-only pilot launcher, optional private-pilot API password.

## Validation completed

- 14 automated tests passed using synthetic data and a fake provider.
- Tested low/moderate/high profiles, 2/3 and 7/8 score boundaries, reverse-scored items, unknown/missing answers, final Q20 response, clarification, retries, paused writes, stale revisions, ownership isolation, provider failure, job restart recovery, transcript evidence, invalid citations, encrypted storage/reload, transcription endpoint behavior, and PDF generation.
- Next.js production build passed.
- In-browser completion of all 20 synthetic Liam responses, persisted session recovery, review navigation, background report generation, and report rendering.
- Mobile onboarding and report checked at 390px; no horizontal page overflow.
- All five pages of the generated demo PDF visually reviewed; headings, quotes, tables, and footers are readable and unclipped.

## Explicit boundaries / outstanding release gates

- The supplied environment file is now accessible and contains an OPENAI_API_KEY assignment; the application has not yet been verified using it. Real therapist/evaluator responses, model access, transcription, and generated speech still need live-provider testing. There is no claim that fake-provider tests validate model quality.
- Physical microphone permissions, capture quality, interruption behavior, and playback require real-device testing. The UI and endpoint paths are implemented; no user's microphone was activated during development.
- The official M-CHAT-R Follow-Up instrument is not implemented. Moderate initial scores clearly show Follow-Up pending; an AI clarification is not substituted for that instrument.
- Live guide responses appear after structured output validation. Session/report state streams over SSE; partial model JSON is not displayed.
- Simulation deliberately uses stored fictional caregiver observations and an offline report template. It does not invent AI clinical analysis.
- This is a local research pilot, not a public or clinically validated service. Qualified review of interpretations/recommendations, instrument permissions, production authentication/operations, and hosting review remain necessary before that use.

See ../README.md for startup and secure API configuration instructions.
