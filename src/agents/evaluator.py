"""Evaluator Agent - Provides explainable ASD screening assessment."""

import json
from typing import List, Dict, Generator, Optional
from pathlib import Path

from utils.openai_client import OpenAIClient
from utils.mchat_scorer import MCHATScorer

# RAG imports - optional, graceful fallback if not available
try:
    from utils.rag_engine import get_rag_engine, RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False


class EvaluatorAgent:
    """Clinical expert providing explainable M-CHAT-R assessment."""

    def __init__(self, client: OpenAIClient, use_rag: bool = True):
        """Initialize the Evaluator Agent.

        Args:
            client: OpenAI client for generating explanations.
            use_rag: Whether to use RAG for clinical evidence retrieval.
        """
        self.client = client
        self.scorer = MCHATScorer()
        self.use_rag = use_rag and RAG_AVAILABLE

        # Initialize RAG engine if available
        self.rag_engine: Optional[RAGEngine] = None
        if self.use_rag:
            try:
                self.rag_engine = get_rag_engine()
                if self.rag_engine.get_stats()['total_chunks'] == 0:
                    print("Warning: RAG index is empty. Run build_index.py to populate it.")
                    self.use_rag = False
            except Exception as e:
                print(f"Warning: Could not initialize RAG engine: {e}")
                self.use_rag = False

        # Load system prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "evaluator_system.txt"
        with open(prompt_path, 'r') as f:
            self.system_prompt = f.read()

        # Load DSM-5 criteria for reference
        dsm5_path = Path(__file__).parent.parent / "data" / "dsm5_criteria.json"
        with open(dsm5_path, 'r') as f:
            self.dsm5_criteria = json.load(f)

    def _build_retrieval_query(
        self,
        responses: Dict[int, str],
        score_results: Dict
    ) -> str:
        """Build a query for RAG retrieval based on screening results.

        Args:
            responses: Dict of extracted M-CHAT responses.
            score_results: Results from the M-CHAT scorer.

        Returns:
            Query string for RAG retrieval.
        """
        query_parts = ["M-CHAT autism screening"]

        # Add risk level
        risk_level = score_results.get('risk_level', 'unknown')
        query_parts.append(f"{risk_level} risk")

        # Add DSM-5 criteria areas with concerns
        dsm5_concerns = score_results.get('dsm5_concerns', {})
        for criterion in dsm5_concerns:
            if criterion.startswith('A1'):
                query_parts.append("social emotional reciprocity")
            elif criterion.startswith('A2'):
                query_parts.append("nonverbal communication")
            elif criterion.startswith('A3'):
                query_parts.append("relationships")
            elif criterion.startswith('B1'):
                query_parts.append("repetitive behaviors")
            elif criterion.startswith('B4'):
                query_parts.append("sensory")

        # Add some at-risk item domains
        at_risk_items = score_results.get('at_risk_items', [])
        if at_risk_items:
            # Get domains from at-risk questions
            for q_id in at_risk_items[:3]:  # Limit to avoid overly long query
                question = self.scorer.get_question(q_id)
                if question:
                    domain = question.get('domain', '')
                    if domain and domain not in query_parts:
                        query_parts.append(domain)

        return " ".join(query_parts)

    def _get_rag_context(
        self,
        responses: Dict[int, str],
        score_results: Dict
    ) -> str:
        """Retrieve relevant clinical evidence using RAG.

        Args:
            responses: Dict of extracted M-CHAT responses.
            score_results: Results from the M-CHAT scorer.

        Returns:
            Formatted RAG context string.
        """
        if not self.use_rag or not self.rag_engine:
            return ""

        try:
            query = self._build_retrieval_query(responses, score_results)
            results = self.rag_engine.retrieve(query, k=5, threshold=0.0)

            if not results:
                return ""

            return self.rag_engine.format_context(results, max_tokens=1500)
        except Exception as e:
            print(f"Warning: RAG retrieval failed: {e}")
            return ""

    def _build_evaluation_context(
        self,
        conversation_log: List[Dict],
        responses: Dict[int, str],
        child_name: str = "the child"
    ) -> str:
        """Build context for the evaluation prompt.

        Args:
            conversation_log: List of conversation messages.
            responses: Dict of extracted M-CHAT responses.
            child_name: Name of the child.

        Returns:
            Context string for the evaluation.
        """
        # Score the responses
        score_results = self.scorer.score_responses(responses)

        # Format conversation transcript
        transcript = "\n\n".join([
            f"**{msg['speaker'].title()}:** {msg['message']}"
            for msg in conversation_log
        ])

        context = f"""
## Screening Information
- Child's Name: {child_name}
- M-CHAT-R Score: {score_results['total_score']}/20
- Risk Level: {score_results['risk_level']}
- At-Risk Items: {score_results['at_risk_items']}

## Extracted Responses
"""
        for q_id, response in sorted(responses.items()):
            question = self.scorer.get_question(q_id)
            at_risk = self.scorer.is_at_risk(q_id, response)
            context += f"- Q{q_id} ({question['short_form']}): {response.upper()}"
            if at_risk:
                context += " [AT-RISK]"
            context += "\n"

        context += f"""
## DSM-5 Criteria Mapping (from scorer)
"""
        for criterion, items in score_results['dsm5_concerns'].items():
            if items:
                context += f"- {criterion}: Questions {items}\n"
            else:
                context += f"- {criterion}: No direct M-CHAT-R items (assess from interview conversation)\n"

        # Add RAG-retrieved clinical evidence
        rag_context = self._get_rag_context(responses, score_results)
        if rag_context:
            context += f"""
## Supporting Clinical Evidence (from knowledge base)

{rag_context}
"""

        context += f"""
## Full Interview Transcript

{transcript}

---

Please analyze this screening interview and provide a detailed, evidence-based evaluation following the output format specified in your instructions. Use the clinical evidence above to inform your analysis, but do NOT reference internal source labels (e.g., "Source 1") in your output. Integrate clinical knowledge naturally into the text.
"""
        return context

    def generate_evaluation(
        self,
        conversation_log: List[Dict],
        responses: Dict[int, str],
        child_name: str = "the child"
    ) -> str:
        """Generate a complete evaluation report.

        Args:
            conversation_log: List of conversation messages.
            responses: Dict of extracted M-CHAT responses.
            child_name: Name of the child.

        Returns:
            The complete evaluation report.
        """
        context = self._build_evaluation_context(conversation_log, responses, child_name)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context}
        ]

        return self.client.chat(messages, temperature=0.3, max_tokens=16000)

    def generate_evaluation_stream(
        self,
        conversation_log: List[Dict],
        responses: Dict[int, str],
        child_name: str = "the child"
    ) -> Generator[str, None, None]:
        """Generate a streaming evaluation report.

        Args:
            conversation_log: List of conversation messages.
            responses: Dict of extracted M-CHAT responses.
            child_name: Name of the child.

        Yields:
            Chunks of the evaluation report.
        """
        context = self._build_evaluation_context(conversation_log, responses, child_name)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context}
        ]

        for chunk in self.client.chat_stream(messages, temperature=0.3, max_tokens=16000):
            yield chunk

    def get_score_summary(self, responses: Dict[int, str]) -> Dict:
        """Get a quick score summary without full evaluation.

        Args:
            responses: Dict of extracted M-CHAT responses.

        Returns:
            Score results from the deterministic scorer.
        """
        return self.scorer.score_responses(responses)

    def get_dsm5_criteria(self) -> Dict:
        """Get the DSM-5 criteria reference data.

        Returns:
            The DSM-5 criteria dict.
        """
        return self.dsm5_criteria
