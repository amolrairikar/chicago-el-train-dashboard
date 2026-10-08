import logging
import re

# Matches the API key in a request URL's query string, e.g. "?mapid=1&key=abc".
API_KEY_PATTERN = re.compile(r"(?<![A-Za-z])(key=)[^&\s'\"]+")


class RedactingFormatter(logging.Formatter):
    """Masks the CTA API key in log output.

    The key must be sent as a query parameter, so request URLs carrying it can
    surface in urllib3 retry warnings and in connection error tracebacks.
    """

    def format(self, record: logging.LogRecord) -> str:
        return API_KEY_PATTERN.sub(r"\1[REDACTED]", super().format(record))


def configure_logging() -> None:
    """Sends INFO and above to stderr through RedactingFormatter.

    basicConfig is a no-op once the root logger has handlers, so calling this
    from several modules is safe.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(logging.BASIC_FORMAT))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
