"""Centralized Circuit Breaker Manager for sharing states across different gateways."""

import threading

from ..config import settings
from .circuit_breaker import CircuitBreaker  # Fixed import path - using relative import


class CircuitBreakerManager:
    """Manages shared circuit breakers across different LLM gateways."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the circuit breaker manager."""
        if not self._initialized:
            self._circuit_breakers: dict[str, CircuitBreaker] = {}
            self._lock = threading.Lock()
            self._initialized = True

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker by name."""
        with self._lock:
            if name not in self._circuit_breakers:
                self._circuit_breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=getattr(settings, "circuit_breaker_failure_threshold", 3),
                    recovery_timeout=getattr(settings, "circuit_breaker_cooldown_period", 60),
                )
            return self._circuit_breakers[name]

    def get_all_states(self) -> dict[str, dict]:
        """Get the state of all circuit breakers."""
        with self._lock:
            return {
                name: breaker.get_state_info() for name, breaker in self._circuit_breakers.items()
            }

    def reset_breaker(self, name: str) -> bool:
        """Reset a specific circuit breaker."""
        with self._lock:
            if name in self._circuit_breakers:
                self._circuit_breakers[name].reset()
                return True
            return False

    def force_close_breaker(self, name: str) -> bool:
        """Force close a specific circuit breaker."""
        with self._lock:
            if name in self._circuit_breakers:
                self._circuit_breakers[name].force_close()
                return True
            return False


# Global instance
_circuit_breaker_manager = CircuitBreakerManager()


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get the global circuit breaker manager instance."""
    return _circuit_breaker_manager


def get_shared_circuit_breaker(name: str) -> CircuitBreaker:
    """Get a shared circuit breaker instance by name."""
    manager = get_circuit_breaker_manager()
    return manager.get_circuit_breaker(name)
