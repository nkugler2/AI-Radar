"""contracts/scrub.py — Secret detection and scrubbing for README content.

Shared by ingestion (logging) and transform (scrubbing). Add new patterns here
to expand coverage — both layers pick them up automatically.
"""

from __future__ import annotations

import re

# Each entry: pattern_name → {regex pattern, severity level}
# Severity: critical = likely real and dangerous, high = real but possibly rotated,
#           medium = common placeholder format, low = structural only
SECRET_PATTERNS: dict[str, dict] = {
    "github_token": {
        "pattern": r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}",
        "severity": "critical",
    },
    "aws_access_key": {
        "pattern": r"AKIA[0-9A-Z]{16}",
        "severity": "high",
    },
    "openai_api_key": {
        "pattern": r"sk-[A-Za-z0-9]{48}",
        "severity": "high",
    },
    "anthropic_api_key": {
        "pattern": r"sk-ant-[A-Za-z0-9\-_]{90,}",
        "severity": "critical",
    },
    "private_key_header": {
        "pattern": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "severity": "high",
    },
    "slack_token": {
        "pattern": r"xox[baprs]-[0-9A-Za-z\-]{10,}",
        "severity": "medium",
    },
    "stripe_live_key": {
        "pattern": r"sk_live_[A-Za-z0-9]{24}",
        "severity": "critical",
    },
    "google_api_key": {
        "pattern": r"AIza[0-9A-Za-z\-_]{35}",
        "severity": "medium",
    },
}

# If any of these appear in the matched value itself, it is almost certainly
# a documentation example rather than a real credential.
_PLACEHOLDER_RE = re.compile(
    r"your[_\-]|example|placeholder|x{4,}|1234567890|ABCDEF$|TOKEN$",
    re.IGNORECASE,
)

REDACTION_MARKER = "[AI-Radar: {pattern_name} redacted]"


def _is_likely_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(value))


def scan_readme(readme: str) -> list[dict]:
    """Scan a README string for secret patterns.

    Returns a list of findings, each a dict with:
      pattern_name, severity, sample (first 60 chars of match), is_likely_placeholder
    """
    if not readme:
        return []

    findings = []
    for pattern_name, cfg in SECRET_PATTERNS.items():
        for match in re.finditer(cfg["pattern"], readme):
            raw = match.group(0)
            findings.append({
                "pattern_name": pattern_name,
                "severity": cfg["severity"],
                "sample": raw[:60],
                "is_likely_placeholder": _is_likely_placeholder(raw),
            })
    return findings


def scrub_readme(readme: str) -> tuple[str, list[dict]]:
    """Replace all secret pattern matches in readme with a redaction marker.

    Returns (scrubbed_readme, findings) where findings is the same list
    as scan_readme() would return for the original text.
    """
    if not readme:
        return readme, []

    findings = scan_readme(readme)
    scrubbed = readme
    for pattern_name, cfg in SECRET_PATTERNS.items():
        marker = REDACTION_MARKER.format(pattern_name=pattern_name)
        scrubbed = re.sub(cfg["pattern"], marker, scrubbed)

    return scrubbed, findings
