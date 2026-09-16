"""M-CHAT-R scoring logic."""

import json
from typing import Dict, List, Tuple
from pathlib import Path


class MCHATScorer:
    """Deterministic scorer for M-CHAT-R questionnaire."""

    # Items where YES = at-risk (reverse scored)
    REVERSE_SCORED = {2, 5, 12}

    # Risk level thresholds
    LOW_RISK_MAX = 2
    MODERATE_RISK_MAX = 7

    def __init__(self, questions_path: str = None):
        """Initialize the scorer.

        Args:
            questions_path: Path to mchat_questions.json. If None, uses default location.
        """
        if questions_path is None:
            questions_path = Path(__file__).parent.parent / "data" / "mchat_questions.json"

        with open(questions_path, 'r') as f:
            self.questions_data = json.load(f)

        self.questions = {q['id']: q for q in self.questions_data['questions']}

    def is_at_risk(self, question_id: int, response: str) -> bool:
        """Determine if a response indicates at-risk for a specific question.

        Args:
            question_id: The question number (1-20).
            response: The response, either "yes" or "no" (case-insensitive).

        Returns:
            True if the response indicates at-risk, False otherwise.
        """
        response = response.lower().strip()
        if question_id not in self.questions or response not in {'yes', 'no'}:
            raise ValueError('Scoring requires a valid question and a confirmed yes/no answer')

        if question_id in self.REVERSE_SCORED:
            # For items 2, 5, 12: YES = at-risk
            return response == "yes"
        else:
            # For all other items: NO = at-risk
            return response == "no"

    def score_responses(self, responses: Dict[int, str]) -> Dict:
        """Score a complete set of M-CHAT-R responses.

        Args:
            responses: Dict mapping question_id (1-20) to response ("yes"/"no").

        Returns:
            Dict containing:
                - total_score: int (0-20)
                - risk_level: str ("LOW", "MODERATE", "HIGH")
                - at_risk_items: List of question IDs that were at-risk
                - item_scores: Dict mapping question_id to at_risk boolean
                - dsm5_concerns: Dict mapping DSM-5 criteria to relevant at-risk items
        """
        if any(not isinstance(k, int) or not 1 <= k <= 20 for k in responses):
            raise ValueError('Question IDs must be integers from 1 to 20')
        unresolved = [q for q in range(1, 21) if str(responses.get(q, '')).strip().lower() not in {'yes', 'no'}]
        at_risk_items = []
        item_scores = {}

        for q_id in range(1, 21):
            if q_id in responses and q_id not in unresolved:
                is_risk = self.is_at_risk(q_id, responses[q_id])
                item_scores[q_id] = is_risk
                if is_risk:
                    at_risk_items.append(q_id)

        total_score = len(at_risk_items)

        # Determine risk level
        if unresolved:
            risk_level = 'INCOMPLETE'
        elif total_score <= self.LOW_RISK_MAX:
            risk_level = "LOW"
        elif total_score <= self.MODERATE_RISK_MAX:
            risk_level = "MODERATE"
        else:
            risk_level = "HIGH"

        # Map at-risk items to DSM-5 criteria
        dsm5_concerns = self._map_to_dsm5(at_risk_items)

        return {
            "total_score": total_score if not unresolved else None,
            "is_complete": not unresolved,
            "unresolved_items": unresolved,
            "risk_level": risk_level,
            "at_risk_items": at_risk_items,
            "item_scores": item_scores,
            "dsm5_concerns": dsm5_concerns
        }

    def _map_to_dsm5(self, at_risk_items: List[int]) -> Dict[str, List[int]]:
        """Map at-risk items to DSM-5 ASD criteria.

        Args:
            at_risk_items: List of question IDs that were at-risk.

        Returns:
            Dict mapping DSM-5 criteria codes to lists of relevant question IDs.
        """
        dsm5_mapping = {
            "A1": [],  # Social-emotional reciprocity
            "A2": [],  # Nonverbal communication
            "A3": [],  # Relationships
            "B1": [],  # Stereotyped behaviors
            "B2": [],  # Insistence on sameness
            "B3": [],  # Restricted interests
            "B4": []   # Sensory reactivity
        }

        for q_id in at_risk_items:
            question = self.questions.get(q_id)
            if question:
                for criterion in question.get("dsm5_mapping", []):
                    if criterion in dsm5_mapping:
                        dsm5_mapping[criterion].append(q_id)

        return dsm5_mapping

    def get_question(self, question_id: int) -> Dict:
        """Get question details by ID.

        Args:
            question_id: The question number (1-20).

        Returns:
            Question dict with text, examples, domain, etc.
        """
        return self.questions.get(question_id)

    def get_risk_description(self, risk_level: str) -> str:
        """Get the description for a risk level.

        Args:
            risk_level: "LOW", "MODERATE", or "HIGH".

        Returns:
            Description string for the risk level.
        """
        descriptions = {
            "LOW": "Low Risk: If child is younger than 24 months, rescreen after second birthday. No further action required unless surveillance indicates risk for ASD.",
            "MODERATE": "Moderate likelihood: Administer the formal M-CHAT-R Follow-Up for elevated-likelihood items. If two or more remain elevated, refer for early intervention and diagnostic evaluation.",
            "INCOMPLETE": "Incomplete screening: review missing or uncertain answers before assigning a final score.",
            "HIGH": "High Risk: Refer immediately for diagnostic evaluation and early intervention services."
        }
        return descriptions.get(risk_level, "Unknown risk level")

    def format_results(self, results: Dict) -> str:
        """Format scoring results as a readable string.

        Args:
            results: Results dict from score_responses().

        Returns:
            Formatted string representation.
        """
        lines = [
            f"M-CHAT-R Score: {results['total_score']}/20",
            f"Risk Level: {results['risk_level']}",
            f"",
            self.get_risk_description(results['risk_level']),
            f"",
            f"At-Risk Items ({len(results['at_risk_items'])}): {results['at_risk_items']}"
        ]

        if results['dsm5_concerns']:
            lines.append("")
            lines.append("DSM-5 Criteria Concerns:")
            for criterion, items in results['dsm5_concerns'].items():
                lines.append(f"  {criterion}: Questions {items}")

        return "\n".join(lines)
