"""The defect being fixed: `log.info` reached nobody, in every service."""
from __future__ import annotations

import json
import logging

import pytest

from ds_obs.logging import ProbeAccessFilter, configure_logging


@pytest.fixture(autouse=True)
def _restore_logging():
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    access = logging.getLogger("uvicorn.access")
    saved_access = (list(access.handlers), list(access.filters), access.propagate)
    yield
    root.handlers, root.level = saved
    access.handlers, access.filters, access.propagate = saved_access


def _access_record(path: str, status: int) -> logging.LogRecord:
    """Shaped like uvicorn's own access record: (host, method, path, http, status)."""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", path, "1.1", status),
        None,
    )


class TestLevel:
    def test_info_is_emitted(self, capsys, monkeypatch):
        """The whole bug. Unconfigured, the root logger drops INFO.

        A successful crawl logged at INFO and was therefore indistinguishable
        from a crawl that never ran — only the failure path spoke.
        """
        monkeypatch.delenv("DS_LOG_LEVEL", raising=False)
        configure_logging("ds-test")
        log = logging.getLogger("federated_catalog.crawler")
        log.info("Crawl complete: 2 datasets")
        assert "Crawl complete: 2 datasets" in capsys.readouterr().out

    def test_level_comes_from_the_environment(self, capsys, monkeypatch):
        monkeypatch.setenv("DS_LOG_LEVEL", "WARNING")
        configure_logging("ds-test")
        log = logging.getLogger("x")
        log.info("quiet")
        log.warning("loud")
        out = capsys.readouterr().out
        assert "quiet" not in out
        assert "loud" in out

    def test_an_unknown_level_falls_back_to_info_rather_than_crashing(
        self, capsys, monkeypatch
    ):
        """A typo in a deployment's env must not take the service down."""
        monkeypatch.setenv("DS_LOG_LEVEL", "VERBOSE")
        configure_logging("ds-test")
        logging.getLogger("x").info("still here")
        assert "still here" in capsys.readouterr().out

    def test_calling_twice_does_not_duplicate_every_line(self, capsys, monkeypatch):
        monkeypatch.delenv("DS_LOG_LEVEL", raising=False)
        configure_logging("ds-test")
        configure_logging("ds-test")
        logging.getLogger("x").info("once")
        assert capsys.readouterr().out.count("once") == 1


class TestFormat:
    def test_text_carries_the_service_name(self, capsys, monkeypatch):
        monkeypatch.delenv("DS_LOG_FORMAT", raising=False)
        configure_logging("ds-provenance")
        logging.getLogger("x").info("hello")
        assert "[ds-provenance]" in capsys.readouterr().out

    def test_json_is_one_object_per_line(self, capsys, monkeypatch):
        monkeypatch.setenv("DS_LOG_FORMAT", "json")
        configure_logging("ds-connector")
        logging.getLogger("connector.sync").info("synced")
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["service"] == "ds-connector"
        assert payload["logger"] == "connector.sync"
        assert payload["message"] == "synced"
        assert payload["level"] == "INFO"

    def test_json_carries_ds_prefixed_extras_as_fields(self, capsys, monkeypatch):
        monkeypatch.setenv("DS_LOG_FORMAT", "json")
        configure_logging("ds-connector")
        logging.getLogger("x").info("crawled", extra={"ds_provider": "did:web:a"})
        assert json.loads(capsys.readouterr().out.strip())["provider"] == "did:web:a"


class TestProbeSuppression:
    def test_a_successful_probe_is_dropped(self):
        f = ProbeAccessFilter()
        assert f.filter(_access_record("/health", 200)) is False
        assert f.filter(_access_record("/metrics", 200)) is False

    def test_a_failing_probe_is_kept(self):
        """The line you actually need is the one where the probe stopped passing."""
        assert ProbeAccessFilter().filter(_access_record("/health", 503)) is True

    def test_a_query_string_does_not_evade_the_match(self):
        assert ProbeAccessFilter().filter(_access_record("/health?x=1", 200)) is False

    def test_real_traffic_is_never_dropped(self):
        f = ProbeAccessFilter()
        assert f.filter(_access_record("/catalog", 200)) is True
        assert f.filter(_access_record("/health-check-dataset", 200)) is True

    def test_an_unexpected_record_shape_is_kept(self):
        """A filter that guesses wrong should add noise, never remove signal."""
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, "odd", (), None
        )
        assert ProbeAccessFilter().filter(record) is True

    def test_suppression_is_opt_out(self, monkeypatch):
        monkeypatch.setenv("DS_LOG_ACCESS_HEALTH", "true")
        configure_logging("ds-test")
        filters = logging.getLogger("uvicorn.access").filters
        assert not any(isinstance(f, ProbeAccessFilter) for f in filters)


class TestNoisyThirdParties:
    def test_httpx_is_quieted_unless_debugging(self, monkeypatch):
        """One INFO line per outbound request drowns the event that caused them."""
        monkeypatch.setenv("DS_LOG_LEVEL", "INFO")
        configure_logging("ds-test")
        assert logging.getLogger("httpx").level == logging.WARNING

        monkeypatch.setenv("DS_LOG_LEVEL", "DEBUG")
        configure_logging("ds-test")
        assert logging.getLogger("httpx").level == logging.DEBUG


def test_uvicorn_shares_our_handler_so_one_format_reaches_the_log(monkeypatch):
    """Otherwise a container emits two formats — what "coordinated" rules out."""
    configure_logging("ds-test")
    root_handler = logging.getLogger().handlers[0]
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        assert logger.handlers == [root_handler]
        assert logger.propagate is False
