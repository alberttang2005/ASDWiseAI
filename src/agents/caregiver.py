"""Caregiver Agent - Simulates parent responses based on child profile."""

import json
import re
from typing import List, Dict, Generator, Optional
from pathlib import Path

from utils.openai_client import OpenAIClient


class CaregiverAgent:
    """Parent/guardian responding to M-CHAT-R screening questions."""

    def __init__(self, client: OpenAIClient, profile_path: Optional[str] = None):
        """Initialize the Caregiver Agent.

        Args:
            client: OpenAI client for generating responses.
            profile_path: Path to the child profile JSON file.
        """
        self.client = client
        self.profile: Optional[Dict] = None
        self.conversation_history: List[Dict[str, str]] = []

        # Load system prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "caregiver_system.txt"
        with open(prompt_path, 'r') as f:
            self.system_prompt = f.read()

        # Load profile if provided
        if profile_path:
            self.load_profile(profile_path)

    def load_profile(self, profile_path: str):
        """Load a child profile from JSON file.

        Args:
            profile_path: Path to the profile JSON file.
        """
        with open(profile_path, 'r') as f:
            self.profile = json.load(f)
        self.conversation_history = []

    def load_profile_by_name(self, profile_name: str):
        """Load a profile by name from the profiles directory.

        Args:
            profile_name: Name of the profile (e.g., 'low_likelihood', 'high_likelihood').
        """
        profile_dir = Path(__file__).parent.parent / "profiles"
        profile_path = profile_dir / f"{profile_name}.json"
        self.load_profile(str(profile_path))

    def reset(self):
        """Reset conversation history while keeping the profile."""
        self.conversation_history = []

    def _build_profile_context(self) -> str:
        """Build context string from the loaded profile."""
        if not self.profile:
            return "No profile loaded. Respond as a typical parent."

        profile_text = f"""
Child Profile:
- Name: {self.profile['child_info']['name']}
- Age: {self.profile['child_info']['age_months']} months
- Gender: {self.profile['child_info']['gender']}

Background: {self.profile.get('additional_context', 'No additional context.')}

Behavioral Patterns (use these to guide your responses):
"""
        for q_id, behavior in self.profile['behaviors'].items():
            profile_text += f"- {q_id}: Response tendency: {behavior['response']}"
            if 'detail' in behavior:
                profile_text += f" - {behavior['detail']}"
            profile_text += "\n"

        return profile_text

    def _strip_question_tags(self, message: str) -> str:
        """Remove [Q#] tracking tags from therapist messages.

        These are internal tracking markers not visible to a real caregiver.
        """
        return re.sub(r'\[Q\d+\]\s*', '', message)

    def generate_response(self, therapist_message: str) -> str:
        """Generate a response to the therapist's question.

        Args:
            therapist_message: The therapist's question or statement.

        Returns:
            The caregiver's response.
        """
        # Strip question tracking tags before adding to history
        clean_message = self._strip_question_tags(therapist_message)
        self.conversation_history.append({
            "role": "user",
            "content": clean_message
        })

        # Build messages for API call
        system_content = self.system_prompt + "\n\n" + self._build_profile_context()
        messages = [
            {"role": "system", "content": system_content}
        ]
        messages.extend(self.conversation_history)

        # Generate response
        response = self.client.chat(messages, temperature=0.8)

        # Add to conversation history
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def generate_response_stream(self, therapist_message: str) -> Generator[str, None, None]:
        """Generate a streaming response to the therapist's question.

        Args:
            therapist_message: The therapist's question or statement.

        Yields:
            Chunks of the caregiver's response.
        """
        # Strip question tracking tags before adding to history
        clean_message = self._strip_question_tags(therapist_message)
        self.conversation_history.append({
            "role": "user",
            "content": clean_message
        })

        # Build messages for API call
        system_content = self.system_prompt + "\n\n" + self._build_profile_context()
        messages = [
            {"role": "system", "content": system_content}
        ]
        messages.extend(self.conversation_history)

        # Generate streaming response
        full_response = ""
        for chunk in self.client.chat_stream(messages, temperature=0.8):
            full_response += chunk
            yield chunk

        # Add to conversation history
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })

    def get_child_name(self) -> str:
        """Get the child's name from the profile.

        Returns:
            The child's name, or 'the child' if no profile loaded.
        """
        if self.profile:
            return self.profile['child_info']['name']
        return "the child"

    def get_profile_info(self) -> Optional[Dict]:
        """Get the loaded profile information.

        Returns:
            The profile dict, or None if no profile loaded.
        """
        return self.profile

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get the full conversation history.

        Returns:
            List of message dicts with role and content.
        """
        return self.conversation_history.copy()
