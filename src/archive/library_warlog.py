"""Extract the published, redacted narrative without executing source scripts."""
import json
import re


def extract_warlog(payload: bytes) -> str:
    html = payload.decode("utf-8-sig")
    match = re.search(r'\bvar\s+summary\s*=\s*("(?:\\.|[^"\\])*")\s*;', html)
    if not match:
        raise ValueError("War Diary page has no published summary")
    narrative = json.loads(match.group(1))
    if not narrative.strip():
        raise ValueError("War Diary narrative is empty")
    return narrative
