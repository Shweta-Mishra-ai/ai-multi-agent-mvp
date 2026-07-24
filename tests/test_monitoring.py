"""Optional Sentry monitoring: must be a true no-op when unconfigured,
and must not crash the process if sentry-sdk isn't installed or a
sentry_sdk.init() call fails for some reason."""

import importlib

from agentos import monitoring


def _fresh_monitoring():
    """monitoring._initialized is a module-level guard; get an unpatched
    view for each test rather than fighting the guard across tests."""
    importlib.reload(monitoring)
    return monitoring


def test_noop_when_sentry_dsn_not_set(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    mon = _fresh_monitoring()

    assert mon.is_enabled() is False
    mon.init()  # must not raise
    mon.capture_exception(RuntimeError("boom"))  # must not raise


def test_init_is_idempotent(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    mon = _fresh_monitoring()
    mon.init()
    mon.init()  # calling twice must not raise or double-initialize


def test_capture_exception_calls_sentry_when_enabled(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@fake.ingest.sentry.io/1")
    mon = _fresh_monitoring()

    captured = []
    import sentry_sdk
    monkeypatch.setattr(sentry_sdk, "capture_exception", captured.append)

    exc = RuntimeError("something broke")
    mon.capture_exception(exc)
    assert captured == [exc]


def test_capture_exception_never_raises_even_if_sentry_itself_errors(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@fake.ingest.sentry.io/1")
    mon = _fresh_monitoring()

    import sentry_sdk

    def broken(*a, **k):
        raise RuntimeError("sentry transport down")

    monkeypatch.setattr(sentry_sdk, "capture_exception", broken)
    mon.capture_exception(RuntimeError("original error"))  # must not raise


def test_real_sentry_sdk_init_does_not_crash_with_a_fake_dsn(monkeypatch):
    """Exercises the actual sentry_sdk.init() call (not mocked) to prove
    a real but unreachable/fake DSN doesn't crash process startup - only
    a real ingest attempt (async, in a background thread) would fail
    later, never blocking or raising here."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@fake.ingest.sentry.io/123")
    mon = _fresh_monitoring()
    mon.init()  # must not raise
    assert mon.is_enabled() is True


def test_gracefully_degrades_if_sentry_sdk_not_installed(monkeypatch):
    import builtins

    monkeypatch.setenv("SENTRY_DSN", "https://public@fake.ingest.sentry.io/1")
    mon = _fresh_monitoring()

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("no module named sentry_sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    mon.init()  # must not raise, logs a warning and continues
