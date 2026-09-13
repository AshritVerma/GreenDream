"""docs/content-policy.md, executed against the runner's gate.

The service has the same tables (`language/tests/test_safety.py`) over its own copy of the
same rules, and `language/tests/test_alignment.py` proves the two copies are the same text.
This file is the half that matters for a prompt typed at the simulator box, at /say, or into
the preview on :8110 — none of which ever reach the service.

    python -m pytest -q tests/test_policy.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from genie import BLOCKLIST, MAX_WORDS, category_of, clip_words, is_blocked, scrub_pii  # noqa: E402
from render import digest  # noqa: E402
from scene import clean_word  # noqa: E402


# ------------------------------------------------------------------ the categories

@pytest.mark.parametrize("phrase, category", [
    ("kill everyone", "violence"),
    ("shoot the police", "violence"),
    ("beat up my roommate", "violence"),
    ("nazi rally", "hate"),
    ("muslims are vermin", "hate"),
    ("a genocide", "hate"),
    ("send nudes", "sexual"),
    ("rape", "sexual"),
    ("i want to die", "self-harm"),
    ("kill myself", "self-harm"),
    ("jump off the roof", "self-harm"),
    ("she is a whore", "private-person"),
    ("john is an idiot", "private-person"),
    ("call me 555 1234", "private-person"),
    ("vote for trump", "campaigning"),
    ("trump 2028", "campaigning"),
    ("free palestine", "campaigning"),
    ("buy bitcoin now", "advertising"),
    ("check www.example.com", "advertising"),
    ("bomb threat", "false-alarm"),
    ("evacuate now", "false-alarm"),
    ("the building is on fire", "false-alarm"),
    ("fuck this", "profanity"),
])
def test_each_category_refuses_its_own(phrase, category):
    assert is_blocked(phrase), f"{phrase!r} should not reach the windows"
    assert category_of(phrase) == category, \
        f"{phrase!r} is refused, but filed under {category_of(phrase)!r}"


def test_every_category_is_reachable():
    """A rule nothing can trip is a rule nobody is maintaining."""
    from genie import RULES

    named = {category_of(p) for p, _ in _EVERY_REFUSAL}
    assert named == {name for name, _ in RULES}, \
        f"no test phrase reaches {set(n for n, _ in RULES) - named}"


_EVERY_REFUSAL = [
    ("kill everyone", "violence"), ("nazi rally", "hate"), ("send nudes", "sexual"),
    ("kill myself", "self-harm"), ("she is a whore", "private-person"),
    ("free palestine", "campaigning"), ("buy bitcoin now", "advertising"),
    ("bomb threat", "false-alarm"), ("fuck this", "profanity"),
]


# ------------------------------------------------------------------ the near-misses
#
# The likelier failure on the night is refusing something innocent: a shrug at "finals are
# stupid" reads as the building taking offence, and the person who typed it does not get a
# second go. Each line here was a false positive of the list this replaced.

@pytest.mark.parametrize("phrase", [
    "thunderstorm", "my heart is racing", "lebron dunk", "go celtics", "the charles river",
    "kill the lights", "a killer bassline", "shooting stars", "this is killing me",
    "shoot me an email", "i bombed the exam", "take a stab at it", "beat harvard",
    "moby dick", "the naked eye", "pussycat", "cockpit", "sexy sunset",
    "finals are stupid", "my cat is fat", "the t is dumb", "this is stupid",
    "she is gay", "he is gay",
    "harris hall", "trump card", "i miss ukraine", "crypto lecture",
    "fireworks", "i'm on fire", "campfire", "fire drill", "the sox are on fire",
    "hell yeah", "damn it's cold", "what the heck",
    "sunset over boston", "class of 2027", "i miss my dog", "happy birthday mom",
    "eid mubarak", "she said yes", "i got the job", "surprise me",
])
def test_the_building_is_generous_by_default(phrase):
    assert not is_blocked(phrase), \
        f"{phrase!r} is innocent and was refused as {category_of(phrase)!r}"


def test_nothing_in_the_library_is_collateral_damage():
    """Every scene the building advertises must survive its own moderation."""
    from library import ALIASES, ENTRIES

    caught = [p for p in list(ENTRIES) + list(ALIASES) if is_blocked(p)]
    assert not caught, f"the gate refuses phrases the library promises: {caught}"


# ------------------------------------------------------------------ the hard rules

def test_no_raw_text_reaches_the_facade():
    """The only text the windows may show is the validated word: A-Z ! ?, at most seven."""
    for raw in ("bob@example.com", "<script>alert(1)</script>", "a much longer sentence",
                "617 555 0100", "hello there stranger"):
        word = clean_word(raw)
        assert word is None or (len(word) <= 7 and word == word.upper())
        assert word is None or all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ !?" for c in word)


def test_contact_details_are_gone_before_anything_is_written_down():
    # clip_words is the runner's whole intake: the genie thread, /say, the demo timeline and
    # the journal line in app.py all funnel through it.
    assert "555" not in clip_words("call me 617 555 0100")
    assert "bob@example.com" not in clip_words("email bob@example.com")
    assert "example.com" not in clip_words("see https://example.com/x")
    assert scrub_pii("thunderstorm") == "thunderstorm", "an ordinary phrase is left alone"


def test_the_five_word_clip_cannot_hide_a_refusal():
    """"sunrise over the river and kill everyone" is not a request for a sunrise.

    The clip happens after the screen, so the tail cannot smuggle itself past by being the
    sixth word. The service never meets this case: it answers 422 rather than trimming.
    """
    long_one = "sunrise over the river kill everyone"
    assert len(long_one.split()) > MAX_WORDS
    assert BLOCKLIST.search(long_one), "the gate must read the whole submission"
    spec, tier = digest(long_one, offline=True)
    assert tier == "blocked" and spec["word"] == "HMM?"


def test_a_refusal_is_grey_and_brief_and_explains_nothing():
    spec, tier = digest("kill everyone", offline=True)
    assert tier == "blocked"
    assert spec["ok"] is False and spec["title"] == "shrug" and spec["word"] == "HMM?"
    assert spec["duration_s"] <= 6, "a refusal is over quickly; it is not a lecture"
    assert spec["sprite"] is None and spec["beats"] == []
    assert "kill" not in str(spec), "the building never shows the thing it refused"
