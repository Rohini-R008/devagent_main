"""
Parses pytest's output to extract structured runtime failures — this is
what actually makes "detect runtime errors" true, rather than just handing
raw stdout to the LLM and hoping it notices.

Relies on pytest's "short test summary info" section, which prints one
line per failure in the form:
    FAILED path/to/test.py::test_name - ErrorType: message
    ERROR path/to/test.py::test_name - ErrorType: message   (collection errors)
"""
import re
from typing import TypedDict

_SUMMARY_LINE_RE = re.compile(
    r"^(?P<kind>FAILED|ERROR)\s+(?P<location>\S+)\s+-\s+(?P<detail>.+)$",
    re.MULTILINE,
)


class RuntimeError_(TypedDict):
    kind: str          # "FAILED" or "ERROR"
    file: str
    test_name: str
    error_type: str
    message: str


def parse_runtime_errors(sandbox_logs: str) -> list[RuntimeError_]:
    """Extract structured failures from pytest's output."""
    errors: list[RuntimeError_] = []

    for m in _SUMMARY_LINE_RE.finditer(sandbox_logs):
        location = m.group("location")
        detail = m.group("detail").strip()

        if "::" in location:
            file_part, test_name = location.split("::", 1)
        else:
            file_part, test_name = location, ""

        if ":" in detail:
            error_type, message = detail.split(":", 1)
            message = message.strip()
        else:
            error_type, message = detail, ""

        errors.append({
            "kind": m.group("kind"),
            "file": file_part,
            "test_name": test_name,
            "error_type": error_type.strip(),
            "message": message,
        })

    return errors
