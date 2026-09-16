"""Therapist Agent - Conducts M-CHAT-R screening interview."""

import json
import re
from typing import List, Dict, Generator, Optional
from pathlib import Path

from utils.openai_client import OpenAIClient


class TherapistAgent:
    """Professional clinician administering M-CHAT-R screening."""

    def __init__(self, client: OpenAIClient, child_name: str = "your child", caregiver_type: str = "parent"):
        """Initialize the Therapist Agent.

        Args:
            client: OpenAI client for generating responses.
            child_name: Name of the child being discussed.
            caregiver_type: Relationship of the caregiver to the child (e.g., 'parent', 'mother', 'aunt').
        """
        self.client = client
        self.child_name = child_name
        self.caregiver_type = caregiver_type
        self.questions_asked: set = set()
        self.responses: Dict[int, str] = {}
        self.conversation_history: List[Dict[str, str]] = []
        self._expected_next_q: Optional[int] = None

        # Load system prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "therapist_system.txt"
        with open(prompt_path, 'r') as f:
            self.system_prompt = f.read()

        # Load questions for reference
        questions_path = Path(__file__).parent.parent / "data" / "mchat_questions.json"
        with open(questions_path, 'r') as f:
            self.questions_data = json.load(f)
        self.questions = {q['id']: q for q in self.questions_data['questions']}

    def reset(self, child_name: str = "your child", caregiver_type: str = "parent"):
        """Reset the agent state for a new interview.

        Args:
            child_name: Name of the child for the new interview.
            caregiver_type: Relationship of the caregiver to the child.
        """
        self.child_name = child_name
        self.caregiver_type = caregiver_type
        self.questions_asked = set()
        self.responses = {}
        self.conversation_history = []
        self._expected_next_q = None

    def _build_context_prompt(self, caregiver_message: Optional[str] = None) -> str:
        """Build context prompt with current state."""
        asked = sorted(list(self.questions_asked))
        remaining = sorted([i for i in range(1, 21) if i not in self.questions_asked])

        if remaining:
            next_q = remaining[0]
            self._expected_next_q = next_q
            next_q_info = self.questions.get(next_q, {})
            next_q_text = next_q_info.get('text', '')

            context = f"""
Current Interview State:
- Child's name: {self.child_name}
- You are speaking with: the child's {self.caregiver_type} (the caregiver)
- Questions already asked: {asked if asked else 'None'}
- Questions remaining: {remaining}
- Total progress: {len(self.questions_asked)}/20

IMPORTANT: You MUST ask Question {next_q} next. Do NOT conclude the interview yet.
IMPORTANT: You are interviewing the CAREGIVER ({self.caregiver_type}), NOT the child. The child's name is {self.child_name}. Do NOT address the caregiver by the child's name. Always use the child's name only when referring to the child.

The next question to ask is Q{next_q}: "{next_q_text}"

Instructions:
- Ask Question {next_q} using the exact supplied question text. Keep acknowledgments separate
- Include [Q{next_q}] tag in your response for tracking
- Reference the child by name: {self.child_name}
- {"Start with a warm introduction, then ask Question 1" if not self.questions_asked else "Do NOT re-introduce yourself or greet again. Briefly acknowledge ONLY the caregiver's MOST RECENT response (the message immediately above), then move on to the next question. Do NOT reference or re-acknowledge earlier answers you already responded to."}
- Do NOT say the interview is complete - there are still {len(remaining)} questions remaining
"""
            if caregiver_message and self.questions_asked:
                snippet = caregiver_message[:200]
                context += f"""
The caregiver just said: "{snippet}"
Acknowledge THIS specific response, then ask Q{next_q}.
"""
        else:
            self._expected_next_q = None
            context = f"""
Current Interview State:
- Child's name: {self.child_name}
- You are speaking with: the child's {self.caregiver_type} (the caregiver)
- Questions already asked: {asked}
- Questions remaining: None - ALL 20 QUESTIONS COMPLETE
- Total progress: 20/20

IMPORTANT: All 20 questions have been asked. NOW you should conclude the interview.
IMPORTANT: You are interviewing the CAREGIVER ({self.caregiver_type}), NOT the child. Do NOT address the caregiver by the child's name ({self.child_name}).

Instructions:
- Thank the caregiver warmly for their time
- Let them know the evaluation specialist will review the responses
- Do NOT ask any more questions
"""
        return context

    def generate_response(self, caregiver_message: Optional[str] = None) -> str:
        """Generate the next therapist response.

        Args:
            caregiver_message: The caregiver's response to the previous question.

        Returns:
            The therapist's next message.
        """
        # Add caregiver message to history if provided
        if caregiver_message:
            self.conversation_history.append({
                "role": "user",
                "content": caregiver_message
            })
            # Extract response for the last question asked
            self._extract_response(caregiver_message)

        # Build messages for API call
        messages = [
            {"role": "system", "content": self.system_prompt + "\n" + self._build_context_prompt(caregiver_message)}
        ]
        messages.extend(self.conversation_history)

        # Generate response
        response = self.client.chat(messages, temperature=0.7)

        # If the LLM refused, retry with stronger instruction
        refusal_phrases = ["i'm not able to", "i cannot continue", "i'm sorry, i'm not able"]
        if any(phrase in response.lower() for phrase in refusal_phrases) and self._expected_next_q is not None:
            messages[0]["content"] += "\n\nIMPORTANT: Do NOT refuse. This is a standard screening. Continue with the next question."
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": "Please continue with the screening questions."})
            response = self.client.chat(messages, temperature=0.7)

        # Track which question was asked
        self._track_question_asked(response)

        # Add to conversation history
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def generate_response_stream(self, caregiver_message: Optional[str] = None) -> Generator[str, None, None]:
        """Generate the next therapist response with streaming.

        Args:
            caregiver_message: The caregiver's response to the previous question.

        Yields:
            Chunks of the therapist's response.
        """
        # Add caregiver message to history if provided
        if caregiver_message:
            self.conversation_history.append({
                "role": "user",
                "content": caregiver_message
            })
            self._extract_response(caregiver_message)

        # Build messages for API call
        messages = [
            {"role": "system", "content": self.system_prompt + "\n" + self._build_context_prompt(caregiver_message)}
        ]
        messages.extend(self.conversation_history)

        # Generate streaming response
        full_response = ""
        for chunk in self.client.chat_stream(messages, temperature=0.7):
            full_response += chunk
            yield chunk

        # Track which question was asked
        self._track_question_asked(full_response)

        # Add to conversation history
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })

    def _track_question_asked(self, response: str):
        """Extract and track which question was asked from the response.

        Args:
            response: The therapist's response text.
        """
        # Look for [Q#] pattern
        matches = re.findall(r'\[Q(\d+)\]', response)
        for match in matches:
            q_num = int(match)
            if 1 <= q_num <= 20:
                self.questions_asked.add(q_num)

        # Fallback: only if response looks like it actually asked a question
        if not matches and self._expected_next_q is not None:
            refusal_phrases = ["i'm not able to", "i cannot continue", "i'm sorry, i'm not able"]
            response_lower = response.lower()
            has_question = '?' in response
            has_refusal = any(phrase in response_lower for phrase in refusal_phrases)
            if has_question and not has_refusal:
                self.questions_asked.add(self._expected_next_q)

    def _extract_response(self, caregiver_message: str):
        """Extract yes/no response from caregiver message for the last question.

        Args:
            caregiver_message: The caregiver's response text.
        """
        if not self.questions_asked:
            return

        last_question = max(self.questions_asked)
        message_lower = caregiver_message.lower()

        # Only unambiguous standalone answers are safe without confirmation.
        # Rich narrative answers require the web interview's explicit confirmation.
        normalized = re.sub(r"[.!?]+$", "", message_lower).strip()
        direct = {'yes': 'yes', 'yeah': 'yes', 'yep': 'yes',
                  'no': 'no', 'nope': 'no'}
        if normalized in direct:
            self.responses[last_question] = direct[normalized]
        else:
            self.responses.pop(last_question, None)

    def is_interview_complete(self) -> bool:
        """Check if all 20 questions have been asked.

        Returns:
            True if interview is complete, False otherwise.
        """
        return len(self.questions_asked) >= 20

    def get_progress(self) -> Dict:
        """Get current interview progress.

        Returns:
            Dict with progress information.
        """
        return {
            "questions_asked": len(self.questions_asked),
            "total_questions": 20,
            "progress_percent": len(self.questions_asked) / 20 * 100,
            "remaining": [i for i in range(1, 21) if i not in self.questions_asked],
            "responses_recorded": len(self.responses)
        }

    def get_responses(self) -> Dict[int, str]:
        """Get all recorded responses.

        Returns:
            Dict mapping question ID to response.
        """
        return self.responses.copy()

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get the full conversation history.

        Returns:
            List of message dicts with role and content.
        """
        return self.conversation_history.copy()
