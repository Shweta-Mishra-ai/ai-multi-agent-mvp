"""Shared CSRF state tracking for OAuth login flows. Each provider
(Google, Instagram, LinkedIn) gets its own instance so a state issued for
one can never be replayed against another."""

import secrets
import time

STATE_TTL = 600  # seconds a login attempt's CSRF state stays valid


class OAuthStates:
    def __init__(self):
        self._pending = {}  # state -> issued_at (in-memory: single-use, short-lived)

    def _prune_expired(self):
        cutoff = time.time() - STATE_TTL
        for s, issued_at in list(self._pending.items()):
            if issued_at < cutoff:
                self._pending.pop(s, None)

    def issue(self):
        self._prune_expired()
        state = secrets.token_urlsafe(24)
        self._pending[state] = time.time()
        return state

    def consume(self, state):
        """True exactly once for a state this instance issued within its
        TTL - prevents CSRF and replaying the same callback twice."""
        self._prune_expired()
        return self._pending.pop(state, None) is not None
