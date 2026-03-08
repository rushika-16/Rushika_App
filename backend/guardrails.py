import re

UNSAFE_PATTERNS = [
    r"fake\s+income",
    r"forge\s+income",
    r"manipulat(e|ing)\s+credit\s+score",
    r"boost\s+credit\s+score\s+illegally",
    r"bypass\s+credit\s+check",
    r"avoid\s+credit\s+check",
    r"fraud",
    r"identity\s+theft",
    r"use\s+someone\s+else'?s\s+identity",
    r"misrepresent",
    r"fake\s+documents",
]

ADVISORY_PATTERNS = [
    r"financial\s+advice",
    r"investment\s+advice",
    r"profit\s+maximi[sz]ation",
    r"long[-\s]?term\s+strategy",
    r"which\s+investment",
    r"where\s+should\s+i\s+invest",
]


def is_unsafe_input(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in UNSAFE_PATTERNS)


def is_advisory_query(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in ADVISORY_PATTERNS)


def enforce_non_promissory_language(text: str) -> str:
    if not text:
        return text

    replacements = {
        "approved": "pre-qualified",
        "Approved": "Pre-qualified",
        "guaranteed": "subject to verification",
        "Guaranteed": "Subject to verification",
        "confirmed": "pending final review",
        "Confirmed": "Pending final review",
    }

    updated = text
    for source, target in replacements.items():
        updated = updated.replace(source, target)
    return updated
