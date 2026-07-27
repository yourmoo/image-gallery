"""Structured logging for the image gallery.

The brief requires structured logs that are readable from container output and
carry enough context to diagnose failures. A plain ``format`` string cannot do
that safely: any quote, backslash, or newline in a log message would produce
invalid JSON. This formatter serialises through ``json.dumps`` instead, so the
output is always parseable.
"""

import json
import logging


class JsonFormatter(logging.Formatter):
    """Render each log record as a single line of JSON.

    Extra context is included by passing ``extra={...}`` at the call site; any
    key that is not part of the standard ``LogRecord`` attribute set is merged
    into the output object.
    """

    # Attributes present on every LogRecord. Anything outside this set was
    # supplied by the caller via `extra=` and is worth emitting.
    _STANDARD_ATTRS = frozenset(
        {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in self._STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)
