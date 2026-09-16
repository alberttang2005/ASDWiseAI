# ASDWise Haven: caregiver-facing screening application plan

Updated September 16, 2026 following the product clarification: deliver a real caregiver-facing screening web application, not a demo. The September 15 local pilot is the implementation baseline, not the finished product. See IMPLEMENTATION_STATUS.md for completed work and remaining verification. This plan describes intended work; it does not claim production readiness.

## 1. Target experience

Keep the selected Haven design. A caregiver enters a child's preferred name, age in months, and caregiver relationship, chooses typing or microphone input, and talks with an explicitly labeled AI screening guide (the conversational guide). The guide asks the screening questions, clarifies ambiguous answers, and records caregiver-confirmed responses. After review, the caregiver generates a detailed, explainable screening report and downloads a PDF.

Remove demo selection, synthetic profiles, simulation controls, and offline template reports from the caregiver-facing application. Keep fictional fixtures only in development and automated tests; production APIs must reject synthetic-session creation and demo actions, not merely hide their controls. Preserve unrelated Streamlit research code. Keep pause, resume, review, and deletion for real screening sessions. Label the agent as an AI screening guide throughout.

## 2. Reuse and changes by source module

| Existing source | Proposed use | Required changes |
| --- | --- | --- |
| `src/app.py` | Functional reference for setup, controls, conversation, evaluation, and report | Move UI behavior into Haven components; extract reusable report logic without importing Streamlit into the API |
| `src/utils/conversation.py` | Interview orchestration and simulation | Serialize session state; explicit current question and confirmed-answer state; safe retries and completion |
| `src/agents/therapist.py` | Empathetic text conversation and streaming | Replace substring-based yes/no extraction; allow clarification without advancing; preserve canonical screening wording |
| `src/agents/caregiver.py` | Internal research/test fixtures only | Exclude from the production caregiver workflow and production API |
| `src/utils/mchat_scorer.py` | Deterministic scoring | Validate all 20 answers; preserve unknowns; keep initial and Follow-Up scores separate |
| `src/agents/evaluator.py` | Report reasoning | Return validated structured data with evidence IDs and source citations; require source availability |
| `src/prompts/evaluator_system.txt` | Report section baseline | Remove unsupported criterion-threshold conclusions; add uncertainty, source, and evidence rules |
| `src/utils/rag_engine.py` | Existing retrieval infrastructure | Inspect ingestion and metadata before reuse; filter to approved sources with page/criterion references |
| `website-designs/app/page.js` | Haven visual foundation | Split into onboarding, interview, voice controls, response review, and report components |

## 3. Architecture

Use the existing Python agents behind a FastAPI service. Keep Next.js for the Haven interface and a same-origin API gateway. This avoids porting the clinical workflow into two languages.

Browser -> Next.js gateway -> Python session service -> Therapist Agent / deterministic scorer / Evaluator Agent.

Audio follows browser -> transcription service -> editable transcript -> existing text interview. Therapist text can then be sent to text-to-speech.

Remove `output: 'export'` when adding Next.js server routes. Deploy Next.js and Python as separate services behind one origin. Start locally before choosing production hosting. Keep API secrets on the Python server. Do not expose Python directly to unauthenticated public traffic.

Proposed server-owned records:

- Session: owner, mode, child context, status, current question, instrument/source versions, revision.
- Turn: stable ID, role, question ID, text, input modality, timestamp; preserve original and caregiver-corrected transcript separately.
- Answer: question ID, yes/no/unknown, caregiver confirmation, supporting turn IDs, notes, revision.
- Report: immutable input revision, deterministic score, validated analysis, references, model/prompt versions, generation status.

Replace the temporary local SQLite deployment with durable production storage (planned Postgres), migrations, backups, and a tested restore procedure. Retain a local development configuration. Store data outside the Google Drive-synced repository and outside git. Require production identity/session access controls, ownership checks on every read/write/export, encryption appropriate to storage/hosting, and documented retention and deletion controls. Select a recoverable caregiver sign-in or secure resume-link flow before implementation; the existing browser cookie alone does not provide cross-device recovery. Do not store transcripts in browser localStorage or ordinary application logs. Raw recordings are temporary by default; discard app copies after transcription or cancellation and describe provider processing separately.

Suggested API contract:

- `POST /api/sessions`: create a real caregiver screening session.
- `GET /api/sessions/{id}`: resume state and transcript.
- `POST /api/sessions/{id}/turns`: submit text with expected revision and idempotency key.
- `PATCH /api/sessions/{id}/answers/{questionId}`: confirm or correct an answer.
- `POST /api/sessions/{id}/control`: pause, resume, stop, or reset; no production demo actions.
- `POST /api/sessions/{id}/audio/transcriptions`: bounded audio upload.
- `POST /api/sessions/{id}/audio/speech`: speak a server-owned guide message.
- `POST /api/sessions/{id}/reports`: enqueue generation from a frozen response revision.
- `GET /api/sessions/{id}/events`: stream guide and report progress using server-sent events.
- `GET /api/reports/{id}` and `/pdf`: retrieve validated report and download.

Every endpoint validates ownership, payload size, session state, and revision. Use a serialized turn queue per session to prevent double advances. Editing an answer marks prior reports stale; regeneration creates a new version. Generation failures remain retryable without duplicating caregiver messages.

## 4. Voice interaction

Begin with push-to-talk, using browser microphone capture and a transcription -> text agent -> speech pipeline. This fits the existing text Therapist Agent and lets caregivers correct recognition errors before submitting. Continuous hands-free voice can be a later enhancement.

Haven controls:

1. Choose “Type” or “Speak”; ask for microphone permission only after a deliberate recording action.
2. Show recording indicator, elapsed time, stop, and cancel.
3. Stop recording, transcribe, and show editable text. Never silently submit a transcript.
4. Caregiver sends the response; the guide streams its next message.
5. Optional “Read aloud,” replay, mute, and stop playback. Label the voice as AI-generated.
6. Pause stops recording/playback and prevents late responses from advancing the interview.

Support permission denial, no microphone, silence, unsupported recording format, interrupted upload, timeouts, rate limits, and failed playback. Always retain typing as a fallback. Negotiate supported MIME types; limit recording size/duration; release microphone tracks. Require HTTPS outside localhost. Do not infer clinical characteristics from the caregiver's voice or background sounds.

Choose transcription and speech model identifiers at implementation after verifying account access and costs. Retain the current text-model setting initially for comparison; make therapist, evaluator, transcription, and speech models separately configurable.

## 5. Interview and scoring corrections

- Preserve canonical question wording, order, and instrument version; put conversational acknowledgments and clarification outside the scored question. The current prompt asks the LLM to rephrase questions, so this needs deliberate revision.
- Replace earliest-substring yes/no matching with schema-validated interpretation and caregiver confirmation. “Yesterday,” “not sure,” mixed answers, and corrections must not silently determine a score.
- Track questions asked separately from answers confirmed. Q20 must receive a response before closure.
- Store uncertainty explicitly; unresolved items produce an incomplete result, never zero-risk points. Report generation may produce an incomplete summary but no final screening classification.
- Preserve deterministic reverse scoring for items 2, 5, and 12. The LLM cannot change totals or thresholds.
- The current moderate-score description omits the formal M-CHAT-R Follow-Up step. Implement the official Follow-Up decision trees for initial scores 3–7 as a release requirement, after confirming authoritative materials and electronic-use permissions. Pending status is acceptable during development only; it does not satisfy completion of this release scope. Generic AI clarification is not the formal Follow-Up instrument.
- Gather supplemental context where appropriate: frequency, settings, onset, impact, routines, and intensity of interests. Keep these separate from the 20 scored answers; allow “unknown.”
- Confirm instrument version, intended age range, approved wording, and electronic-use permissions before public distribution; do not silently expand the current 16–30-month scope.

## 6. Detailed report matching the supplied example

Use the Liam PDF as a layout and depth reference, not as patient data or a gold-standard clinical conclusion.

Report sections:

1. Header: child context, interview date, mode, completion, report version, and references used.
2. Deterministic M-CHAT-R summary: score out of 20 only when complete, likelihood band, initial vs Follow-Up status, and applicable next step.
3. All 20 item responses: short label, confirmed answer, result, uncertainty, and links to transcript evidence.
4. DSM-5-informed observations: A1, A2, A3 and B1, B2, B3, B4. Each contains status (reported concern / no concern reported / insufficient evidence), interpretation, exact caregiver quotes, question and turn IDs, guideline citations, and missing context.
5. Additional diagnostic context: onset, functional impact, and limitations concerning alternative explanations. Explicitly distinguish information collected from what requires professional assessment; do not assign diagnosis or support-severity levels.
6. Overall synthesis: strengths, reported concerns, conflicting observations, and uncertainty. Do not equate A/B concern counts with satisfying diagnostic criteria.
7. Recommendations: primary recommendation, secondary supports, relevant resources, and follow-up plan. Use approved source-grounded guidance; avoid invented appointments, timelines, or local providers.
8. Screening limitations and references. Optionally include the interview transcript in an export selected by the caregiver.

Render React components from a validated report schema, not arbitrary model-generated HTML. Provide section navigation, expandable evidence, and readable status badges. Generate downloadable PDFs from the same report data with repeating table headings, page numbers, consistent Haven styling, and controlled page breaks. Review every output page for clipping and orphaned headings.

## 7. Grounding in the attached DSM document

The attached document is Laura Carpenter's February 2013 “Guidelines & Criteria Exemplars,” a pre-publication reference that explicitly warns that criteria may change. Register its author, date, title, checksum, page numbers, and criterion tags. Use its examples and interpretation cautions as requested, while checking diagnostic criterion definitions against an authoritative published source; record disagreements rather than merging versions silently.

For this small document, a reviewed criterion-indexed reference bundle plus its general guidelines is sufficient initially. Embedding search is optional; if the existing Chroma retrieval is used, retrieve by approved document/version and criterion, and include the general guidelines for every analysis. If a required reference is unavailable, do not silently produce an apparently grounded report.

Evidence pipeline:

Confirmed answers + transcript -> extracted observations with exact quote spans -> criterion-specific reference passages -> structured analysis -> deterministic and evidence validation -> report.

Validators must ensure quotes exist verbatim, belong to the caregiver, and reference real turns; cited pages exist; score matches the scorer; unsupported claims remain uncertain. Treat retrieved documents and transcripts as source data, never instructions that can override the application's rules.

Specific correction from the supplied sample: its Q3 play observation is reused to establish concerns under B1, B2, and B3. The attached reference cautions against satisfying multiple criteria with the same exemplar and specifically places lining up objects under B1. Ask separate questions about distress with changes and unusual intensity/focus before interpreting B2/B3; otherwise use insufficient evidence. Distinct facets of one observation may be discussed with explicit justification, not automatic triple counting.

## 8. Delivery sequence and acceptance gates

### Phase 1 — Real caregiver workflow and live integration

Remove all demo entry points and production simulation endpoints. Retain Haven, onboarding, consent, typing/voice, confirmation, review, and resume. Explain age eligibility and the distinction between screening and diagnosis before starting. Provide a useful next step for caregivers outside the supported age range. Configure the provided environment file server-side and test the existing provider adapters using fictional data. If the provider is unavailable, show an honest retryable error; never substitute a synthetic report.

Acceptance: a real-mode 20-item interview survives refresh, confirms Q20, handles unknown answers without a final classification, and recovers from retries without duplicate turns. A production API request cannot create a synthetic session. No key appears in browser bundles, logs, or responses. Test live text, transcription, speech, and evaluator calls; physical microphone checks remain a real-device test.

### Phase 2 — Complete screening and evidence-grounded reports

Implement authorized formal Follow-Up flows, separate initial and Follow-Up answers/scores, branch transitions, caregiver corrections, and applicable next steps. Verify instrument wording, intended population, distribution permissions, and scoring against current authoritative materials. Review the supplied draft DSM exemplars alongside an authoritative published reference; record source versions and resolve discrepancies explicitly. Preserve the detailed report design described above, including quotes, uncertainty, strengths, recommendations, and PDF export. Explain criterion observations in plain language; do not imply that the AI establishes diagnostic criteria or a diagnosis.

Acceptance: test each implemented Follow-Up branch, scoring boundaries, corrections, incomplete paths, and report regeneration. Every quote and citation validates. A failed AI analysis remains retryable while confirmed answers stay saved. Caregivers can review results and download a readable PDF. Qualified review of report interpretations and recommendations is a release gate; synthetic agreement is not clinical validation.

### Phase 3 — Production privacy, access, and durable storage

Implement the selected caregiver authentication/resume design, durable storage migrations, session ownership, secure expiring access, consent version records, retention jobs, deletion, backups, and restore. Decide what child information is necessary and minimize collection. Explain app and provider handling of transcripts/audio in the privacy notice. Keep raw recordings transient by default. Cover reports and derived records in deletion; document backup expiry. Keep sensitive information out of analytics and routine logs.

Acceptance: independent users cannot retrieve, alter, stream, or download each other's records. Expired sessions and access links fail correctly. Restore and retention/deletion tests pass. Data survives application restarts and deployment. Hosting region, provider handling, applicable privacy obligations, and public policy text are reviewed for the intended audience before collecting real caregiver information.

### Phase 4 — Reliability, accessibility, and operational controls

Replace process-local report tasks and locks with durable jobs and concurrency controls suitable for the chosen deployment. Add bounded retries, timeouts, per-user request and spending limits, safe error reporting, service health checks, and redacted monitoring. Test keyboard and screen-reader use, responsive layouts, permission denial, silence, interrupted uploads, and session recovery. Use the same confirmed-text path for typed and spoken responses.

Acceptance: failed/restarted workers recover jobs without duplicate reports; concurrent requests cannot advance a session twice; voice cancellation releases the microphone and preserves work; stale reports are clearly identified. Accessibility and supported real-device/browser checks pass. Abuse controls constrain unauthenticated and authenticated costs.

### Phase 5 — Deployment and release verification

Choose hosting for Next.js, private Python API, database, and durable workers. Configure HTTPS, deployment secrets, environment separation, migrations, backups, monitoring, and rollback. Run end-to-end fictional caregiver sessions on the deployed environment before real-data use. Complete clinical-content, instrument-permission, privacy, and security release reviews. Start with a controlled real-caregiver release and track failures and usability feedback.

Acceptance: typed and microphone sessions produce reviewed downloadable reports on the deployed site; recovery, ownership, retention/deletion, and report-job checks pass. No synthetic controls or fixture data appear in the production app. Record the evidence and owner for each release gate; do not label unfinished work production-ready.

## 9. Credentials, decisions, and scope

The user-provided rich-text environment file has been converted to plain text at `/Users/amyzhuang/Documents/APPs/ASDWise/.env`; an `OPENAI_API_KEY` assignment is present. This confirms file access only, not key validity, model access, or a successful live call. Load it through the existing explicit server configuration for local verification. Use deployment secrets in production. Never expose the key in client code, logs, reports, or chat.

Confirmed: Haven design; real caregiver-facing screening; detailed evidence-grounded reports; typing and editable microphone transcription; no caregiver-facing demo; no diagnosis or support-severity assignment.

Planning assumptions: English first, existing instrument age scope until verified, no default raw-audio retention, Next.js plus Python, and managed durable storage. Decisions still needed before their dependent implementation: hosting and data region, caregiver sign-in/resume method, retention duration, operating budget, and qualified content/release reviewer. Present concrete options when these decisions become necessary; they do not block removal of demo flows or fictional-data live integration tests.

Out of initial scope: continuous hands-free voice, additional languages, clinician portals, and claims of clinical validation. Research fixtures remain internal test assets only.

## 10. Implementation checkpoints and Git delivery

User-authorized destination: https://github.com/alberttang2005/ASDWiseAI.git.

After each completed major implementation, run the relevant checks, inspect the changes for credentials and sensitive caregiver data, commit the scoped implementation, and push to this repository. The user has authorized these milestone pushes; routine pushes do not require repeated confirmation. Report the pushed branch/commit and verification results. If authentication or repository access blocks a push, state the specific blocker.

The current origin points to the separate ASDWise repository. Use a dedicated remote for ASDWiseAI, verify its existing branches/history before the first push, and use a codex/ branch unless the user specifies otherwise. Preserve existing remote configuration, unrelated working changes, and remote history; do not force-push. Never include environment files, keys, local session databases, or real caregiver records.

## Sources checked

- Source application: `src/app.py`, `src/utils/conversation.py`, `src/agents/therapist.py`, `src/agents/evaluator.py`, `src/utils/mchat_scorer.py`, `src/utils/openai_client.py`, and `src/prompts/evaluator_system.txt`.
- User report: `paper/IEEE/figures/full_report_liam.pdf`, especially item results, criterion evidence, and recommendations.
- User DSM reference: `References/DSM-5(ASD.Guidelines)Feb2013.pdf`, especially general guidelines and B1–B3 distinctions.
- OpenAI audio architecture: https://developers.openai.com/api/docs/guides/audio
- Official M-CHAT-R/F scoring: https://www.mchatscreen.com/mchat-rf/scoring/
- CDC published DSM-5 criteria overview: https://www.cdc.gov/autism/hcp/diagnosis/index.html
