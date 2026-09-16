"""Conversation orchestrator for managing agent interactions."""

import json
from enum import Enum
from typing import List, Dict, Generator, Tuple, Optional, Callable
from datetime import datetime
from pathlib import Path

from utils.openai_client import OpenAIClient
from agents.therapist import TherapistAgent
from agents.caregiver import CaregiverAgent


class ConversationState(Enum):
    """States for conversation control flow."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETE = "complete"


class ConversationManager:
    """Orchestrates the conversation between Therapist and Caregiver agents."""

    def __init__(self, model: str = "gpt-5-nano"):
        """Initialize the conversation manager.

        Args:
            model: The OpenAI model to use for both agents.
        """
        self.client = OpenAIClient(model=model)
        self.therapist: Optional[TherapistAgent] = None
        self.caregiver: Optional[CaregiverAgent] = None
        self.conversation_log: List[Dict] = []
        self.is_complete = False

        # Control state
        self._state = ConversationState.IDLE
        self._last_therapist_message: str = ""
        self._pending_turn: Optional[str] = None  # 'therapist' or 'caregiver'
        self._awaiting_closing: bool = False  # True after Q20 answered, waiting for closing

    @property
    def state(self) -> ConversationState:
        """Get current conversation state."""
        return self._state

    def setup_simulation(self, profile_name: str):
        """Set up a simulated conversation with a predefined profile.

        Args:
            profile_name: Name of the profile ('low_likelihood', 'moderate_likelihood', 'high_likelihood').
        """
        # Initialize caregiver with profile
        self.caregiver = CaregiverAgent(self.client)
        self.caregiver.load_profile_by_name(profile_name)

        # Initialize therapist with child's name and caregiver type
        child_name = self.caregiver.get_child_name()
        caregiver_type = self.caregiver.profile.get('caregiver_info', {}).get('type', 'parent') if self.caregiver.profile else 'parent'
        self.therapist = TherapistAgent(self.client, child_name=child_name, caregiver_type=caregiver_type)

        # Reset state
        self.conversation_log = []
        self.is_complete = False
        self._state = ConversationState.IDLE
        self._last_therapist_message = ""
        self._pending_turn = "therapist"  # Therapist starts
        self._awaiting_closing = False

    def setup_interactive(self, child_name: str = "your child"):
        """Set up an interactive conversation where user plays caregiver.

        Args:
            child_name: Name of the child to use in questions.
        """
        self.therapist = TherapistAgent(self.client, child_name=child_name)
        self.caregiver = None  # User will provide responses
        self.conversation_log = []
        self.is_complete = False
        self._state = ConversationState.IDLE
        self._last_therapist_message = ""
        self._pending_turn = "therapist"
        self._awaiting_closing = False

    def pause(self):
        """Pause the conversation."""
        if self._state == ConversationState.RUNNING:
            self._state = ConversationState.PAUSED

    def resume(self):
        """Resume a paused conversation."""
        if self._state == ConversationState.PAUSED:
            self._state = ConversationState.RUNNING

    def stop(self):
        """Stop the conversation (can be resumed from current point)."""
        if self._state in (ConversationState.RUNNING, ConversationState.PAUSED):
            self._state = ConversationState.STOPPED

    def reset(self):
        """Reset the conversation to the beginning."""
        if self.therapist:
            child_name = self.therapist.child_name
            if self.caregiver:
                # Simulation mode - reload profile
                profile = self.caregiver.get_profile_info()
                self.caregiver.reset()
                self.therapist.reset(child_name)
            else:
                # Interactive mode
                self.therapist.reset(child_name)

        self.conversation_log = []
        self.is_complete = False
        self._state = ConversationState.IDLE
        self._last_therapist_message = ""
        self._pending_turn = "therapist"
        self._awaiting_closing = False

    def can_continue(self) -> bool:
        """Check if conversation can continue (not paused/stopped)."""
        return self._state == ConversationState.RUNNING

    def is_paused(self) -> bool:
        """Check if conversation is paused."""
        return self._state == ConversationState.PAUSED

    def is_stopped(self) -> bool:
        """Check if conversation is stopped."""
        return self._state == ConversationState.STOPPED

    def run_single_turn(self) -> Optional[Tuple[str, str]]:
        """Run a single turn of the conversation.

        Returns:
            Tuple of (speaker, message) or None if cannot continue.
        """
        if not self.therapist or (self._pending_turn == "caregiver" and not self.caregiver):
            return None

        if self._state == ConversationState.COMPLETE:
            return None

        if self._state in (ConversationState.PAUSED, ConversationState.STOPPED):
            return None

        self._state = ConversationState.RUNNING

        if self._pending_turn == "therapist":
            # Generate therapist message
            if not self.conversation_log:
                # First message - no caregiver response yet
                message = self.therapist.generate_response()
            else:
                # Get last caregiver message
                last_caregiver_msg = None
                for msg in reversed(self.conversation_log):
                    if msg["speaker"] == "caregiver":
                        last_caregiver_msg = msg["message"]
                        break
                message = self.therapist.generate_response(last_caregiver_msg)

            self._log_message("therapist", message)
            self._last_therapist_message = message

            # Check if this was the closing message (all questions asked and awaiting closing)
            if self._awaiting_closing:
                # This was the closing message - interview is now complete
                self.is_complete = True
                self._state = ConversationState.COMPLETE
                return ("therapist", message)

            # Check if all questions have been asked (Q20 just asked)
            if self.therapist.is_interview_complete():
                # Q20 was just asked, need caregiver response then closing
                self._awaiting_closing = True

            self._pending_turn = "caregiver"
            return ("therapist", message)

        else:  # caregiver turn
            if not self.caregiver:
                return None

            message = self.caregiver.generate_response(self._last_therapist_message)
            self._log_message("caregiver", message)
            self._pending_turn = "therapist"

            return ("caregiver", message)

    def run_simulation(self) -> Generator[Tuple[str, str], None, None]:
        """Run a full simulated conversation between agents.

        Yields:
            Tuples of (speaker, message) for each turn in the conversation.
        """
        if not self.therapist or not self.caregiver:
            raise ValueError("Must call setup_simulation() first")

        self._state = ConversationState.RUNNING

        # Therapist starts the conversation
        therapist_message = self.therapist.generate_response()
        self._log_message("therapist", therapist_message)
        self._last_therapist_message = therapist_message
        yield ("therapist", therapist_message)

        # Continue until interview is complete or stopped
        while not self.therapist.is_interview_complete():
            # Check for pause/stop
            if self._state == ConversationState.PAUSED:
                self._pending_turn = "caregiver"
                return
            if self._state == ConversationState.STOPPED:
                self._pending_turn = "caregiver"
                return

            # Caregiver responds
            caregiver_message = self.caregiver.generate_response(therapist_message)
            self._log_message("caregiver", caregiver_message)
            yield ("caregiver", caregiver_message)

            # Check for pause/stop
            if self._state == ConversationState.PAUSED:
                self._pending_turn = "therapist"
                return
            if self._state == ConversationState.STOPPED:
                self._pending_turn = "therapist"
                return

            # Therapist asks next question
            therapist_message = self.therapist.generate_response(caregiver_message)
            self._log_message("therapist", therapist_message)
            self._last_therapist_message = therapist_message
            yield ("therapist", therapist_message)

        # All 20 questions asked - get final caregiver response to Q20
        caregiver_message = self.caregiver.generate_response(therapist_message)
        self._log_message("caregiver", caregiver_message)
        yield ("caregiver", caregiver_message)

        # Therapist gives closing message
        therapist_message = self.therapist.generate_response(caregiver_message)
        self._log_message("therapist", therapist_message)
        yield ("therapist", therapist_message)

        # Interview complete - do NOT continue after closing
        self.is_complete = True
        self._state = ConversationState.COMPLETE

    def run_simulation_stream(
        self,
        on_therapist_chunk: Optional[Callable[[str], None]] = None,
        on_caregiver_chunk: Optional[Callable[[str], None]] = None
    ) -> Generator[Tuple[str, str, bool], None, None]:
        """Run a streaming simulated conversation.

        Args:
            on_therapist_chunk: Callback for each therapist token.
            on_caregiver_chunk: Callback for each caregiver token.

        Yields:
            Tuples of (speaker, chunk, is_complete) for streaming updates.
        """
        if not self.therapist or not self.caregiver:
            raise ValueError("Must call setup_simulation() first")

        self._state = ConversationState.RUNNING

        # Therapist starts
        therapist_message = ""
        for chunk in self.therapist.generate_response_stream():
            therapist_message += chunk
            if on_therapist_chunk:
                on_therapist_chunk(chunk)
            yield ("therapist", chunk, False)
        yield ("therapist", "", True)  # Signal message complete
        self._log_message("therapist", therapist_message)
        self._last_therapist_message = therapist_message

        # Continue conversation
        while not self.therapist.is_interview_complete():
            # Check for pause/stop
            if self._state == ConversationState.PAUSED:
                self._pending_turn = "caregiver"
                return
            if self._state == ConversationState.STOPPED:
                self._pending_turn = "caregiver"
                return

            # Caregiver responds
            caregiver_message = ""
            for chunk in self.caregiver.generate_response_stream(therapist_message):
                caregiver_message += chunk
                if on_caregiver_chunk:
                    on_caregiver_chunk(chunk)
                yield ("caregiver", chunk, False)
            yield ("caregiver", "", True)
            self._log_message("caregiver", caregiver_message)

            # Check for pause/stop
            if self._state == ConversationState.PAUSED:
                self._pending_turn = "therapist"
                return
            if self._state == ConversationState.STOPPED:
                self._pending_turn = "therapist"
                return

            # Therapist continues
            therapist_message = ""
            for chunk in self.therapist.generate_response_stream(caregiver_message):
                therapist_message += chunk
                if on_therapist_chunk:
                    on_therapist_chunk(chunk)
                yield ("therapist", chunk, False)
            yield ("therapist", "", True)
            self._log_message("therapist", therapist_message)
            self._last_therapist_message = therapist_message

        # All 20 questions asked - get final caregiver response to Q20
        caregiver_message = ""
        for chunk in self.caregiver.generate_response_stream(therapist_message):
            caregiver_message += chunk
            if on_caregiver_chunk:
                on_caregiver_chunk(chunk)
            yield ("caregiver", chunk, False)
        yield ("caregiver", "", True)
        self._log_message("caregiver", caregiver_message)

        # Therapist gives closing message
        therapist_message = ""
        for chunk in self.therapist.generate_response_stream(caregiver_message):
            therapist_message += chunk
            if on_therapist_chunk:
                on_therapist_chunk(chunk)
            yield ("therapist", chunk, False)
        yield ("therapist", "", True)
        self._log_message("therapist", therapist_message)

        # Interview complete - do NOT continue after closing
        self.is_complete = True
        self._state = ConversationState.COMPLETE

    def get_therapist_question(self) -> str:
        """Get the next therapist question (for interactive mode).

        Returns:
            The therapist's next question.
        """
        if not self.therapist:
            raise ValueError("Must call setup_interactive() first")

        message = self.therapist.generate_response()
        self._log_message("therapist", message)
        return message

    def get_therapist_question_stream(self) -> Generator[str, None, None]:
        """Get the next therapist question with streaming.

        Yields:
            Chunks of the therapist's question.
        """
        if not self.therapist:
            raise ValueError("Must call setup_interactive() first")

        full_message = ""
        for chunk in self.therapist.generate_response_stream():
            full_message += chunk
            yield chunk
        self._log_message("therapist", full_message)

    def submit_user_response(self, response: str) -> str:
        """Submit a user response and get next therapist question.

        Args:
            response: The user's response to the previous question.

        Returns:
            The therapist's next question.
        """
        if not self.therapist:
            raise ValueError("Must call setup_interactive() first")

        self._log_message("caregiver", response)
        message = self.therapist.generate_response(response)
        self._log_message("therapist", message)

        if self.therapist.is_interview_complete():
            self.is_complete = True
            self._state = ConversationState.COMPLETE

        return message

    def _log_message(self, speaker: str, message: str):
        """Log a message to the conversation history.

        Args:
            speaker: Either 'therapist' or 'caregiver'.
            message: The message content.
        """
        self.conversation_log.append({
            "speaker": speaker,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    def get_conversation_log(self) -> List[Dict]:
        """Get the full conversation log.

        Returns:
            List of message dicts with speaker, message, and timestamp.
        """
        return self.conversation_log.copy()

    def get_responses(self) -> Dict[int, str]:
        """Get the extracted M-CHAT-R responses.

        Returns:
            Dict mapping question ID to response.
        """
        if not self.therapist:
            return {}
        return self.therapist.get_responses()

    def get_progress(self) -> Dict:
        """Get interview progress.

        Returns:
            Progress dict from therapist agent.
        """
        if not self.therapist:
            return {"questions_asked": 0, "total_questions": 20, "progress_percent": 0}
        progress = self.therapist.get_progress()
        progress["state"] = self._state.value
        return progress

    def get_state_info(self) -> Dict:
        """Get detailed state information.

        Returns:
            Dict with state details for UI display.
        """
        return {
            "state": self._state.value,
            "is_complete": self.is_complete,
            "pending_turn": self._pending_turn,
            "can_pause": self._state == ConversationState.RUNNING,
            "can_resume": self._state == ConversationState.PAUSED,
            "can_stop": self._state in (ConversationState.RUNNING, ConversationState.PAUSED),
            "can_reset": self._state != ConversationState.IDLE or len(self.conversation_log) > 0,
            "can_start": self._state == ConversationState.IDLE,
            "can_continue": self._state in (ConversationState.STOPPED, ConversationState.PAUSED) and not self.is_complete
        }

    def save_conversation(self, filepath: Optional[str] = None) -> str:
        """Save the conversation log to a JSON file.

        Args:
            filepath: Path to save the file. If None, uses default location.

        Returns:
            The path where the file was saved.
        """
        if filepath is None:
            logs_dir = Path(__file__).parent.parent / "logs"
            logs_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = logs_dir / f"conversation_{timestamp}.json"

        output = {
            "timestamp": datetime.now().isoformat(),
            "state": self._state.value,
            "profile": self.caregiver.get_profile_info() if self.caregiver else None,
            "responses": self.get_responses(),
            "progress": self.get_progress(),
            "conversation": self.conversation_log
        }

        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)

        return str(filepath)
