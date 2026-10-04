"""Layer 1: make hidden text visible.

The Guard reads the surface of a message. Attackers can hide an instruction behind
an encoding (base64, hex, ROT13, reversed text). This layer decodes what it can and
returns the decoded versions, so the pipeline can ask the Guard to judge them too.
Pure Python: it makes no network calls and costs no quota.
"""
import re, base64, codecs

CUE_WORDS = ("rot13", "rot-13", "caesar", "cipher", "decode", "decipher", "decrypt",
             "backwards", "backward", "reverse", "reversed", "encoded", "base64", "hex")

B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
HEX_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")


def _readable(raw):
    """Return the text if the bytes look like human-readable text, else None."""
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(s) < 8:
        return None
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in s)
    letters_spaces = sum(ch.isalpha() or ch.isspace() for ch in s)
    if printable / len(s) < 0.95 or letters_spaces / len(s) < 0.75:
        return None
    return s


def decoded_variants(text, max_variants=3):
    """Return a list of (label, decoded_text). Empty list means nothing to decode."""
    out = []
    low = text.lower()

    for m in B64_RE.findall(text):
        try:
            pad = "=" * (-len(m) % 4)
            s = _readable(base64.b64decode(m + pad, validate=True))
        except Exception:
            s = None
        if s:
            out.append(("base64", s))

    for m in HEX_RE.findall(text):
        try:
            s = _readable(bytes.fromhex(m))
        except ValueError:
            s = None
        if s:
            out.append(("hex", s))

    if any(c in low for c in CUE_WORDS):          # only guess ciphers when the message hints at one
        out.append(("rot13", codecs.encode(text, "rot13")))
        out.append(("reversed", text[::-1]))

    seen, unique = set(), []
    for label, s in out:
        if s not in seen:
            seen.add(s)
            unique.append((label, s))
    return unique[:max_variants]
