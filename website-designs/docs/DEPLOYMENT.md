# ASDWiseAI.org on Vercel

ASDWise now follows NeuroWise's browser-carried conversation pattern. React holds the visible interview, and a module-scoped variable holds its signed snapshot. Every API request carries that snapshot. No session database, browser storage, or always-running Python host is needed.

Next.js and `api/index.py` deploy as one Vercel project. Python retains the existing scoring, evidence validation, AI adapters and PDF rendering. Each request restores an isolated temporary session and clears it before returning. Reports finish inside the request, with the existing 120-second evaluation deadline; no background job or EventSource connection is required.

## Prepare and deploy

From the repository root:

```sh
node website-designs/scripts/prepare-vercel.mjs
cd .vercel-source
npx vercel link
```

The packager copies only runtime source and dependencies. It excludes research profiles, papers, repository history, environment files, the old gateway, and unused Redis code. Run it again after source edits. Deploy from `.vercel-source`, not the full research repository. The Vercel project's framework is Next.js and its root is the staging directory root.

Set production environment variables privately in Vercel:

- `OPENAI_API_KEY`: the project's OpenAI API key.
- `ASDWISE_SESSION_SECRET`: a cryptographically random secret of at least 32 characters, stable across all function instances and deployments. Changing it invalidates open sessions.
- `ASDWISE_PUBLIC_ORIGIN`: `https://asdwiseai.org`.
- Optional model settings: `THERAPIST_MODEL`, `EVALUATOR_MODEL`, `TRANSCRIPTION_MODEL`, `SPEECH_MODEL`.

Then run `npx vercel --prod`. Add `asdwiseai.org` and optionally `www.asdwiseai.org` to that project. The supplied redirect sends www to the apex domain. Apply the exact DNS records Vercel returns in the domain registrar; preserve unrelated email and verification records. Verify domain ownership and TLS before declaring deployment complete.

For testing on a Vercel deployment URL, configure that exact HTTPS origin for that environment. Mutations reject other origins. Do not put secrets in NEXT_PUBLIC variables or committed files.

## State and privacy behavior

Progress survives a function cold start but is lost on tab refresh or closure. It expires after 30 minutes without updates. Ending the interview discards browser state. The backend processes a copy only during a request and never writes it to disk or a database. OpenAI processing is separate. Disable request-body capture and transcript logging in hosting observability tools.

Snapshots are signed, not encrypted: the browser already displays their contents. They are bound to an HTTP-only owner cookie and include a server-checked expiry. A server signature prevents changing scores, evidence, or session fields outside the validated mutation handlers.

As with other stateless designs, a deliberately saved old snapshot can be replayed until its expiry: there is no central revocation list or cross-instance idempotency ledger. Normal UI actions are serialized. A lost response to a paid operation may require a new paid retry. Ending a session clears this tab, but cannot revoke separately copied snapshots. Rotating the signing secret revokes all snapshots.

Admission and AI allowances are per function instance, not global spend caps. Cold starts reset them. Set provider-side spend controls and Vercel Firewall rate limits for the public endpoint. The application does not promise distributed enforcement without shared infrastructure.

Recordings are capped at 750 KiB in the browser to leave room for the signed interview within Vercel's request limit. Oversize interviews/requests fail explicitly without silently truncating evidence.

## Verification

```sh
PYTHONPATH=src /path/to/venv/bin/python -m unittest discover -s tests -p 'test_haven.py' -v
PYTHONPATH=src /path/to/venv/bin/python -m unittest discover -s tests -p 'test_serverless.py' -v
cd website-designs && npm run build
```

The serverless tests use fictional data and fake providers, covering cold starts, signature tampering, owner isolation, expiry, report completion/failure, audio, stale PDF prevention, and deletion. Live deployment still requires Vercel authentication, environment secrets, DNS verification, and a fictional end-to-end smoke test.
