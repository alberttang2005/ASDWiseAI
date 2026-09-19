# Three caregiver perspectives — fictional UX evaluation

## Method

These are scripted, fictional walkthroughs, not interviews with real caregivers and not clinical validation. Do not present the findings as actual user opinions or satisfaction scores.

Each scenario uses the real Python API and configured live OpenAI guide/evaluator. It completes 20 initial-screening items: six narrative submissions (Q1, Q3, Q8, Q10, Q12, Q19) and fourteen quick-answer confirmations. It also tests pause/resume, supplemental context, report generation, PDF response, and explicit clearing. Caregiver-confirmed answers are scripted, not automatically determined by the model. No microphone or usability task timing with real people is tested. Backend latency excludes typing, reading, and browser interaction time.

The runner is `tests/ux/run_caregiver_perspectives.py`. Live calls are opt-in and incur API usage. Only fictional data is written to its explicitly selected output file. The application continues to use temporary memory-only state.

## Scenarios

| Perspective | Observation scope | UX challenge |
| --- | --- | --- |
| Daycare educator | Eight weeks of weekday group-classroom observations | Cannot infer parent hearing concerns, home behavior, or activities not offered at daycare; three answers intentionally remain unknown. |
| Mother | Frequent home observations, several reported concerns | Needs understandable results, emotionally considerate language, and concrete next steps without a diagnostic claim. |
| Father | Mostly evenings/weekends and quiet one-to-one play | Reports a different response-to-name pattern from his partner; needs guidance about observation context without dismissing either caregiver. |

These are deliberately different fictional children and response patterns. Score differences must not be interpreted as effects of caregiver gender or role.

## Original results (before fixes)

All three completed the initial questionnaire and pause/resume checks. Two of three generated validated reports and downloadable PDFs. All three cleared their temporary state after testing.

| Perspective | Initial result | Report/PDF | Measured backend elapsed time |
| --- | --- | --- | --- |
| Daycare educator | Incomplete; Q2, Q19, Q20 unknown | Passed | 325 seconds total; evaluator 257 seconds |
| Mother | 19/20, high initial likelihood | Passed | 258 seconds total; evaluator 180 seconds |
| Father | 0/20, low initial likelihood | Failed: evaluator API timeout | 338 seconds total, including failed generation |

Initial scores are properties of scripted fictional answers, not clinical conclusions. Timing includes live API waits and test polling but excludes human reading/typing. Only one attempt per scenario was included; 2/3 is an observed outcome, not an estimated population success rate. Guide responses took 7.68–18.40 seconds across these runs. Median guide times were 9.55 seconds (daycare), 13.45 (mother), and 10.37 (father). Tests were concurrent, so these timings are not isolated performance benchmarks.

## Perspective-specific findings

### Daycare educator

**Observed:** The guide acknowledged classroom-only knowledge and accepted unknowns. The report explicitly described its single-setting limits and did not produce a final initial score. However, the guide repeatedly asked whether daycare information should be considered inconclusive, including when the educator had supplied a direct observation. Its Q19 response offered a future checklist instead of simply helping finish the current question.

**Inferred user need:** “Let me report what I actually observe, and let me say when I have not had the opportunity to observe something.” This is an analyst-written interpretation, not a quote from a human participant.

**Improve:** Gather observation setting and familiarity once at onboarding. Distinguish not observed from an uncertain interpretation, while retaining unknown scoring. Acknowledge the scope without repeatedly asking permission to use it. Display caregiver relationship and observation setting in the report header. Use caregiver-inclusive language around canonical questionnaire text.

### Mother

**Observed:** All six guide responses stayed on the current item; the report validated and included the caregiver's concerns. Generation took approximately three minutes. The summary used clinical wording such as “deficits in social reciprocity and nonverbal communication” and “repetitive, nonfunctional play.” Its only listed strength was walking.

**Inferred user need:** “Explain what this means and what I can do next, without making me feel that the tool has already diagnosed my child.” This is simulated feedback, not a human opinion.

**Improve:** Lead with a short, plain-language summary of reported observations and an actionable next step. Keep technical criterion discussion expandable. Acknowledge uncertainty and the caregiver's stated worry without inventing reassuring strengths. Provide useful progress/status information while the report is being generated.

### Father

**Observed:** At Q10, the guide appropriately recognized that quiet play and busy routines can produce different observations and suggested documenting both perspectives. It then offered a template rather than directly resolving how the current question should be answered. At Q19 it incorrectly said: “I noticed you referred to Riley as 'she' while you are listed as the father.” Those statements are compatible. The evaluator subsequently timed out; no report or PDF was released.

**Inferred user need:** “Respect the situations I know, include my partner's observations without choosing a winner, and let me finish without irrelevant questions.” This is simulated feedback, not a human opinion.

**Improve:** Explicitly separate caregiver relationship from child pronouns. Use neutral child references when pronouns are unnecessary. Preserve conflicting observations with their setting and source; do not reduce disagreement to an unsupported yes/no suggestion. Keep clarification focused on the current screening item. Improve report timeout handling before inviting real users.

## Prioritized improvements

1. **P0 — Report reliability:** The father run failed after several minutes. Introduce a bounded generation deadline and a specific retryable timeout state, measure provider retries and token usage without logging caregiver text, and re-test richer reports. Do not weaken evidence validation or replace failed reports with demo text.
2. **P0 — Caregiver/child identity distinction:** Add a regression case for a father describing a daughter (and other relationship/pronoun combinations). Explicitly prohibit inferring child gender from caregiver role. The observed question was irrelevant and could undermine trust.
3. **P1 — Observation scope and source:** Collect setting, length of acquaintance, and whether an observation is firsthand. Carry this context into the guide and report. Reconcile differences by documenting them, not by deciding which caregiver is correct.
4. **P1 — Focused clarification:** Avoid optional template/checklist offers in the middle of the 20 items. Clarification should explain the current question or acknowledge that the caregiver cannot answer it.
5. **P1 — Readable, emotionally considerate reports:** Put reported observations and next steps first; use plain language and reserve technical criteria for details. Distinguish lack of evidence from absence of concern.
6. **P2 — Role-inclusive surrounding copy:** The relationship field accepts an educator, but onboarding still says “your child.” Adapt surrounding UI copy without casually rewriting standardized question wording.

## Test limitations and next validation cycle

- These are API-driven workflow tests plus an interface-source review, not three browser-based human usability sessions. They cannot measure real caregiver comprehension, comfort, accessibility, or satisfaction.
- Some base fixtures included park, vacuum, or daycare examples outside the newly prefixed observation scope. Those mixed-setting inputs limit interpretation of scope-related model responses. In particular, mentioning park or vacuum examples was not invented by the guide. Clean up the fixtures before using them as strict context-grounding regression cases.
- The father/child pronoun error is independently valid: a father's use of “she” for his child is not inconsistent, regardless of the other fixture examples.
- Keep these original results as a baseline. Re-run cleaned, internally consistent scenarios after fixes, and include an explicit retry of the timed-out father report as a separate attempt.
- A later real caregiver study should include an educator and parents with differing observation contexts, with consent and a separate research protocol. Do not interpret these simulations as endorsement by those groups.

Structured fictional evidence is in `FICTIONAL_RUN_RESULTS.json`. It includes guide responses, timings, result status, and report summaries. No real caregiver data or API credentials are included.

## September 18 verification after fixes

All six requested UX changes are implemented. The final three live fictional runs passed every recorded check, including valid reports, PDF responses, preserved observation context and unknowns, and explicit clearing. Evaluator times were 21.61 seconds (daycare), 19.21 seconds (mother), and 23.11 seconds (father). Initial results remain incomplete, high (19), and low (0), respectively. The evaluator now defaults to GPT-5 mini with bounded reasoning, selects original evidence IDs rather than recreating quotes, and receives one bounded validation repair attempt under the report deadline.

See `FIX_VERIFICATION.json` for the synthetic inputs, outputs, and checks. The final question-filter adjustment also has a regression test; the complete suite passes 27 tests. The three PDFs were rendered and visually inspected. Prior release limitations above still apply.
