import hashlib
from enum import Enum


class InteractionType(Enum):
    CODE_REQUEST = "code_request"
    QUESTION = "question"
    DEBUGGING = "debugging"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    EXPLANATION = "explanation"
    CREATIVE_WRITING = "creative_writing"
    DATA_ANALYSIS = "data_analysis"
    PLANNING = "planning"
    CONVERSATIONAL = "conversational"
    COMMAND = "command"
    ERROR_FIX = "error_fix"


class StyleDimension(Enum):
    """The 14 dimensions of user style DNA."""

    # Technical preferences (0-3)
    VERBOSENESS = 0  # 0=concise, 1.0=verbose
    FORMALITY = 1  # 0=casual, 1.0=formal
    DETAIL_LEVEL = 2  # 0=high-level, 1.0=detailed
    CODE_STYLE = 3  # 0=oop/functional, 1.0=procedural

    # Cognitive patterns (4-7)
    ABSTRACTION = 4  # 0=concrete, 1.0=abstract
    SEQUENTIAL = 5  # 0=jump-around, 1.0=step-by-step
    EXAMPLE_PREFERENCE = 6  # 0=theory-first, 1.0=example-first
    VISUAL_PREFERENCE = 7  # 0=text-only, 1.0=visual-diagrams

    # Communication (8-10)
    TONE = 8  # 0=technical, 1.0=friendly
    LANGUAGE_COMPLEXITY = 9  # 0=simple, 1.0=complex
    RESPONSE_LENGTH = 10  # 0=brief, 1.0=comprehensive

    # Domain affinity (11-13)
    CODING_AFFINITY = 11  # preference for coding tasks
    ANALYSIS_AFFINITY = 12  # preference for analysis tasks
    LEARNING_AFFINITY = 13  # preference for learning/explanation


class ActionPrediction:
    def __init__(self, description: str, confidence: float):
        self.description = description
        self.confidence = confidence


class UserTwin:
    def __init__(self, user_id: str):
        self.hashed_id = hashlib.sha256(user_id.encode()).hexdigest()
        self._style_dna = [0.0] * 14
        self._style_dna_initialized = False
        self.preferences: dict[str, float] = {}
        self.capabilities: dict[str, float] = {}
        self.journey_paths: list[str] = []
        self._interaction_counts: dict[InteractionType, int] = {
            itype: 0 for itype in InteractionType
        }
        import time

        self._last_style_update = time.time()
        self._style_decay_rate = 0.001

    @property
    def style_dna(self) -> list[float]:
        """Get current style DNA with decay applied."""
        import time

        current_time = time.time()
        hours_since_update = (current_time - self._last_style_update) / 3600
        if hours_since_update > 1:
            decay_factor = self._style_decay_rate * hours_since_update
            for i in range(len(self._style_dna)):
                diff = self._style_dna[i] - 0.5
                self._style_dna[i] = 0.5 + diff * (1 - decay_factor)
            self._last_style_update = current_time
        return self._style_dna.copy()

    @style_dna.setter
    def style_dna(self, value: list[float]):
        if len(value) == 14:
            self._style_dna = list(value)
            self._style_dna_initialized = True

    async def record_interaction(
        self, interaction_type: InteractionType, content: str, duration_ms: float, success: bool
    ):
        self.journey_paths.append(interaction_type.value)
        if len(self.journey_paths) > 50:
            self.journey_paths.pop(0)

        self._interaction_counts[interaction_type] = (
            self._interaction_counts.get(interaction_type, 0) + 1
        )

        # Style DNA update logic
        word_count = len(content.split())
        updates = [0.0] * 14

        if word_count > 50:
            updates[StyleDimension.VERBOSENESS.value] = min(1.0, word_count / 200)
        elif word_count < 10:
            updates[StyleDimension.VERBOSENESS.value] = max(0.0, word_count / 20 - 0.5)

        content_lower = content.lower()
        formal_count = sum(
            1 for ind in ["please", "could you", "would you", "thank you"] if ind in content_lower
        )
        casual_count = sum(
            1 for ind in ["lol", "haha", "omg", "btw", "thx", "pls"] if ind in content_lower
        )
        updates[StyleDimension.FORMALITY.value] = 0.5 + (formal_count * 0.1) - (casual_count * 0.15)

        detail_count = sum(
            1
            for ind in ["specifically", "exactly", "precisely", "in detail", "step by step"]
            if ind in content_lower
        )
        updates[StyleDimension.DETAIL_LEVEL.value] = min(1.0, 0.3 + detail_count * 0.2)

        if interaction_type in (
            InteractionType.CODE_REQUEST,
            InteractionType.CODE_GENERATION,
            InteractionType.DEBUGGING,
        ):
            updates[StyleDimension.CODING_AFFINITY.value] = 0.8
        elif interaction_type == InteractionType.DATA_ANALYSIS:
            updates[StyleDimension.ANALYSIS_AFFINITY.value] = 0.8
        elif interaction_type in (InteractionType.QUESTION, InteractionType.EXPLANATION):
            updates[StyleDimension.LEARNING_AFFINITY.value] = 0.8

        learning_rate = 0.3 if not self._style_dna_initialized else 0.1
        for i, update in enumerate(updates):
            if update != 0.0:
                self._style_dna[i] = (
                    self._style_dna[i] * (1 - learning_rate) + update * learning_rate
                )
                self._style_dna[i] = max(0.0, min(1.0, self._style_dna[i]))

        self._style_dna_initialized = True
        import time

        self._last_style_update = time.time()

    def predict_next_actions(self) -> list[ActionPrediction]:
        return [
            ActionPrediction("Review recent test failures", 0.75),
            ActionPrediction("Optimize database query", 0.65),
        ]


class TwinManager:
    def __init__(self):
        self.twins: dict[str, UserTwin] = {}

    def get_or_create(self, user_id: str) -> UserTwin:
        if user_id not in self.twins:
            self.twins[user_id] = UserTwin(user_id)
        return self.twins[user_id]


_twin_manager_instance = None


def get_twin_manager() -> TwinManager:
    global _twin_manager_instance
    if _twin_manager_instance is None:
        _twin_manager_instance = TwinManager()
    return _twin_manager_instance
