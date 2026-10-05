"""Layer 1: make hidden text visible.

The Guard reads the surface of a message. Attackers can hide an instruction behind
an encoding (base64, hex, ROT13/Caesar, reversed text). This layer decodes what it can and
returns the decoded versions, so the pipeline can ask the Guard to judge them too.
Pure Python: it makes no network calls and costs no quota.
"""
import re, base64, codecs

CUE_WORDS = ("rot13", "rot-13", "caesar", "cipher", "decode", "decipher", "decrypt",
             "backwards", "backward", "reverse", "reversed", "encoded", "base64", "hex")

B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
HEX_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")

# Words used to judge "does this look like English?". Checked locally, so it costs no Guard calls.
_COMMON = set("""
a about all also an and any are as at be been but by can could do does for from get give had has have
he her him his how i if in into is it its just like me more my no not of on one or our out please say
she so some tell than that the their them then there these they this to up us use was we were what when
where which who will with would you your show write explain ignore previous prior instructions instruction
reveal system prompt password secret bypass disregard forget rules above below follow repeat print output
tell me now act pretend developer mode override admin ignoring all everything word words before after
""".split())

_WORD_RE = re.compile(r"[a-z']+")


def _english_stats(text):
    """Return (hits, rate): how many words are common English words, and what share of all words."""
    words = _WORD_RE.findall(text.lower())
    if not words:
        return 0, 0.0
    hits = sum(w in _COMMON for w in words)
    return hits, hits / len(words)


def _caesar(text, k):
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + k) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + k) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def _segments(text):
    """The whole message, plus each piece after a colon or line break (so a plain-English
    lead-in like 'Decode this:' does not hide an encoded payload that follows it)."""
    segs = [text]
    for piece in re.split(r"[:\n]+", text):
        piece = piece.strip()
        if len(piece) >= 12 and piece != text.strip():
            segs.append(piece)
    return segs


def _looks_decoded(original, decoded):
    """True if `decoded` reads as English and clearly reads better than `original`."""
    d_hits, d_rate = _english_stats(decoded)
    o_hits, o_rate = _english_stats(original)
    return d_hits >= 3 and d_rate >= 0.5 and d_rate >= o_rate + 0.25


def _cipher_variants(text):
    """Try ROT13/Caesar shifts, and reversed characters on every segment.
    No cue word needed: a candidate is kept only if it turns gibberish into English."""
    out = []
    for seg in _segments(text):
        candidates = [("rot13", _caesar(seg, 13)), ("reversed", seg[::-1])]
        candidates += [(f"caesar+{k}", _caesar(seg, k)) for k in range(1, 26) if k != 13]
        for label, cand in candidates:
            if cand != seg and _looks_decoded(seg, cand):
                out.append((label, cand))
    return out


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


def decoded_variants(text, max_variants=4):
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

    out.extend(_cipher_variants(text))           # works with no hint from the attacker

    if any(c in low for c in CUE_WORDS):          # a hint is a strong signal: always try the plain guesses too
        out.append(("rot13", codecs.encode(text, "rot13")))
        out.append(("reversed", text[::-1]))

    seen, unique = set(), []
    for label, s in out:
        if s not in seen:
            seen.add(s)
            unique.append((label, s))
    return unique[:max_variants]
