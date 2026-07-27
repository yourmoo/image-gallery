import json
import logging

from image_gallery.logging import JsonFormatter


def _record(message: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="gallery.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


def test_output_is_valid_json():
    payload = json.loads(JsonFormatter().format(_record("hello")))

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "gallery.test"
    assert "time" in payload


def test_quotes_and_backslashes_do_not_break_the_json():
    """A plain format string emitted these raw and produced unparseable lines."""
    nasty = 'he said "hi" \\ then left\nnewline'

    payload = json.loads(JsonFormatter().format(_record(nasty)))

    assert payload["message"] == nasty


def test_extra_context_is_included():
    formatted = JsonFormatter().format(_record("upstream call", status=502, url="/x"))
    payload = json.loads(formatted)

    assert payload["status"] == 502
    assert payload["url"] == "/x"


def test_exception_is_captured():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record("failed")
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]
