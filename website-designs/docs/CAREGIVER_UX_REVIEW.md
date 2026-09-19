# Caregiver experience review

Reviewed the local ASDWise application on September 17, 2026 using a fictional caregiver and child. This is an expert walkthrough, not a study with caregivers or a clinical evaluation. No product code was changed.

## Journey tested

Onboarding → all 20 questions → uncertain quick answer → free-text AI clarification → pause/resume → correction of an earlier answer → completed review → report generation request. Fictional answers exercise interface behavior and do not represent a coherent clinical case. Microphone capture, real-device mobile behavior, and screen-reader operation were not verified.

## What works

The calm green palette, spacious cards, supportive language, and one-question-at-a-time structure make the application approachable. Progress is explicit. Caregivers can choose short answers or describe examples, keep an answer uncertain, and edit recorded answers. No account creation interrupts the journey.

## Prioritized improvements

### 1. Make interruption behavior honest and visible — high priority

The pause message says “Resume whenever you’re ready,” but onboarding says temporary state expires after 30 minutes without updates. Refreshing or leaving also loses access according to the implementation. A caregiver interrupted by their child could reasonably assume pausing protects their work.

Show the actual limit beside Pause and in the paused state. Warn before expiry and offer an explicit continuation action. Explain before starting that this session cannot be resumed after closing or refreshing. Keep the temporary-session design; do not quietly introduce persistent storage.

### 2. Make uncertainty a supported path — high priority

The first “Not sure” click immediately advanced. Help was only available after submitting prose and receiving an AI response. Offer “Help me understand” on every question, and let “Not sure” offer either clarification or continuing with uncertainty. Do not require a guessed yes/no answer to finish.

The AI asked a new clarification question while Yes/No/Not sure buttons still recorded the original screening item. Repeat the original question next to confirmation so caregivers know which question they are answering.

### 3. Make answering and correction predictable — high priority

Short-answer buttons immediately record and advance, whereas prose requires a second confirmation. The page says an answer is not scored until confirmation but does not explain that clicking a short answer is that confirmation.

Use a consistent selected-answer plus Continue pattern, or clearly label direct recording and provide Undo. Add Previous question near the response controls. Move focus and scroll to the next question heading after advancement; current code only explicitly scrolls on view/session changes.

### 4. Reduce review work — high priority

After two uncertain answers, review displayed “2 / 20 recorded” and “20 unresolved,” combining unanswered and uncertain items. Completed review uses abbreviated labels such as “Deaf concern” instead of the full question. The report action sits after 20 rows and four optional text areas.

Separate “not answered” from “not sure.” Lead with the items needing attention, offer full question wording and the original observation, and confirm when edits are applied. Collapse optional context and keep the next action easy to find. Explain before generation what an unresolved answer means for the resulting report.

### 5. Simplify onboarding — medium priority

Add a brief “20 questions → review → downloadable report” overview and a completion-time estimate measured in caregiver testing. The start button and long consent paragraph fell below the initial 1280 × 720 viewport. Break processing information into short, readable points without hiding important disclosures.

Remove the prefilled age of 24 months to reduce accidental submission of the wrong age. Explain that a nickname is sufficient. Reuse space from decorative/support columns for useful preparation information.

### 6. Fix conversation layout — medium priority

The AI reply visibly placed its “AI guide” label beside the paragraph, with cramped wrapping. The `.guide` class styles both the header and guide-role messages as flex rows. Give the identity header a distinct class and stack message labels above their text. Keep the question, clarification, and answer controls visually distinct.

### 7. Make waiting and report delivery reassuring — high priority

Generation showed a disabled “Preparing report…” button and a keep-page-open notice. Add an announced status near the main heading, a clear retry path on failure, and an obvious report-ready state. Do not invent progress percentages or timing guarantees.

Report component inspection shows a large score, all 20 answers, and expanded criterion evidence preceding the full recommendations. Lead with a plain-language summary, what remains uncertain, and next steps. Put detailed evidence in expandable sections and retain an obvious PDF download. This report-layout recommendation is based on source inspection unless a rendered report is subsequently verified.

## Suggested first implementation pass

Address pause/expiry wording, question-level help, consistent answer controls with correction, and a focused review screen. Preserve the existing warm visual identity. Validate the revised flow with caregivers who are interrupted, unsure of an answer, or using a phone with one hand.
