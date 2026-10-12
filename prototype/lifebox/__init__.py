"""Small, authoritative simulation core for independently situated agents."""

from .engine import Engine
from .model import Action, Outcome

__all__ = ["Action", "Engine", "Outcome"]
