from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any


class MarkovChainModel:
    def __init__(self, order: int = 2, min_observations: int = 3):
        self.order = order
        self.min_observations = min_observations
        self._transitions: dict[tuple[str, ...], dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._state_totals: dict[tuple[str, ...], int] = defaultdict(int)
        self._state_counts: dict[str, int] = defaultdict(int)
        self._total_observations = 0
        self._alpha = 0.1

    def observe_transition(self, current_states: tuple[str, ...], next_state: str) -> None:
        key = current_states[-self.order :] if len(current_states) >= self.order else current_states
        self._transitions[key][next_state] += 1
        self._state_totals[key] += 1
        self._state_counts[next_state] += 1
        self._total_observations += 1

    def predict_next(
        self, current_states: tuple[str, ...], top_k: int = 5
    ) -> list[tuple[str, float]]:
        key = current_states[-self.order :] if len(current_states) >= self.order else current_states
        if key in self._transitions and self._state_totals[key] >= self.min_observations:
            predictions = self._calculate_probabilities(key)
            return sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:top_k]
        if len(key) > 1:
            shorter_key = key[1:]
            if shorter_key in self._transitions:
                predictions = self._calculate_probabilities(shorter_key)
                return sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:top_k]
        if self._total_observations > 0:
            common_states = sorted(self._state_counts.items(), key=lambda x: x[1], reverse=True)[
                :top_k
            ]
            total = sum(c for _, c in common_states)
            return [(s, c / total) for s, c in common_states]
        return []

    def _calculate_probabilities(self, key: tuple[str, ...]) -> dict[str, float]:
        transitions = self._transitions[key]
        total = self._state_totals[key]
        vocab_size = len(self._state_counts)
        probabilities = {}
        for state, count in transitions.items():
            prob = (count + self._alpha) / (total + self._alpha * vocab_size)
            probabilities[state] = prob
        return probabilities


class Prediction:
    def __init__(self, key: str, confidence: float, description: str):
        self.key = key
        self.confidence = confidence
        self.description = description


class PredictiveCacheEngine:
    def __init__(self):
        self.cache_client = None
        self.history: dict[str, list] = {}
        self.markov_chain = MarkovChainModel(order=2)

    async def initialize(self, cache_client: Any):
        self.cache_client = cache_client

    async def record_access(self, user_id: str, cache_key: str):
        if user_id not in self.history:
            self.history[user_id] = []

        history = self.history[user_id]
        if history:
            current_states = tuple(history[-self.markov_chain.order :])
            self.markov_chain.observe_transition(current_states, cache_key)

        self.history[user_id].append(cache_key)
        if len(self.history[user_id]) > 100:
            self.history[user_id].pop(0)

    def predict(self, user_id: str, current_key: str) -> list[Prediction]:
        predictions = []
        if user_id in self.history:
            history = tuple(self.history[user_id])
            if len(history) >= self.markov_chain.order:
                markov_preds = self.markov_chain.predict_next(history, top_k=2)
                for state, prob in markov_preds:
                    predictions.append(
                        Prediction(
                            state, prob, f"Markov Chain prediction with {prob:.2f} probability"
                        )
                    )

            if not predictions:
                predictions.append(
                    Prediction(f"next_page:{current_key}", 0.8, "Probable next page visit")
                )
        return predictions

    async def schedule_prefetch(
        self,
        predictions: list[Prediction],
        compute_registry: dict[str, Callable[[], Awaitable[Any]]],
    ):
        decisions = []
        for pred in predictions:
            if pred.confidence > 0.7:
                for reg_key, compute_fn in compute_registry.items():
                    if reg_key.replace("*", "") in pred.key:
                        try:
                            val = await compute_fn()
                            await self.cache_client.set(pred.key, val)
                            decisions.append({"key": pred.key, "status": "prefetched"})
                        except Exception as e:
                            decisions.append({"key": pred.key, "status": f"error: {e}"})
        return decisions


_predictive_engine_instance = None


def get_predictive_engine() -> PredictiveCacheEngine:
    global _predictive_engine_instance
    if _predictive_engine_instance is None:
        _predictive_engine_instance = PredictiveCacheEngine()
    return _predictive_engine_instance
