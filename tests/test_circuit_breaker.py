from agentos.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_opens_after_threshold_consecutive_failures():
    cb = CircuitBreaker(failure_threshold=3, reset_after=60)
    for _ in range(2):
        cb.before_call()          # still closed
        cb.record_failure()
    assert cb.snapshot()["open"] is False

    cb.before_call()
    cb.record_failure()          # 3rd consecutive failure -> opens
    assert cb.snapshot()["open"] is True

    try:
        cb.before_call()
        assert False, "expected CircuitOpenError"
    except CircuitOpenError as e:
        assert "unavailable" in str(e)


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3, reset_after=60)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.snapshot()["consecutive_failures"] == 0
    cb.record_failure()
    cb.record_failure()
    assert cb.snapshot()["open"] is False  # only 2 consecutive since the reset


def test_half_opens_after_cooldown_and_recovers():
    cb = CircuitBreaker(failure_threshold=1, reset_after=0)  # cooldown "elapsed" immediately
    cb.record_failure()
    assert cb.snapshot()["open"] is True

    cb.before_call()  # cooldown of 0s has elapsed -> half-open, should not raise
    cb.record_success()
    assert cb.snapshot() == {"open": False, "consecutive_failures": 0}


def test_llm_chat_records_failure_and_reraises(monkeypatch):
    import agentos.llm as llm_mod
    from agentos import circuit_breaker

    fresh = CircuitBreaker(failure_threshold=2, reset_after=60)
    monkeypatch.setattr(circuit_breaker, "breaker", fresh)
    monkeypatch.setattr(llm_mod, "circuit_breaker", circuit_breaker)

    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("provider down")

    class FakeChatNS:
        completions = FakeCompletions()

    monkeypatch.setattr(llm_mod.client, "chat", FakeChatNS())

    for _ in range(2):
        try:
            llm_mod.chat(messages=[{"role": "user", "content": "hi"}])
        except RuntimeError:
            pass

    assert fresh.snapshot()["open"] is True
    try:
        llm_mod.chat(messages=[{"role": "user", "content": "hi"}])
        assert False, "expected CircuitOpenError once open"
    except circuit_breaker.CircuitOpenError:
        pass
