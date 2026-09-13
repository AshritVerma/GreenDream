"""Text -> scene spec, three tiers: warm library (instant, offline), Claude
(open vocabulary, ~1 s, tool-use so the answer is schema-shaped), lexicon
(affect-only fallback). Always answers; never blocks the frame loop.

Env: ANTHROPIC_API_KEY, optional ANTHROPIC_MODEL (default claude-haiku-4-5).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from typing import Optional, Tuple

from common.inputs import BUS, InputBus

from library import library_spec, lookup
from scene import SCHEMA, SHRUG, validate

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

MAX_WORDS = 5


def clip_words(text: str) -> str:
    """Intake: contact details out, then the five-word budget.

    Every channel funnels through here — the simulator box, /say, the demo timeline, and the
    journal line in app.py — so a caller that forgets to check is scrubbed and truncated
    rather than trusted. The scrub runs first because the journal is an archive and nobody
    typing a phone number at a kiosk means to leave it there; the language service scrubs in
    its own request validator for the same reason. See docs/content-policy.md.
    """
    return " ".join(scrub_pii(text).split()[:MAX_WORDS])

SYSTEM = """You are the imagination of a 21-storey building whose 153 windows (17 rows x 9 columns) are lights.
People on the plaza say at most five words - a thing, a place, a feeling, an event - and you turn them into a short light performance by filling a scene spec.
Rules:
- Read the words as ONE thing and pick its single most recognisable depiction. Bold and simple beats detailed: the tower is 9 windows wide and seen from 300 m away.
- Choreograph, do not pose: give 2-4 'beats' (what builds, what lands, what is left). Start dim (never below 0.3), earn the bright moment, hold 'word' back (null) until the beat that deserves it.
- Use a 'world' when the request is a place/weather; use 'none' + palette + particles for things and feelings.
- A sprite is a judgment call: up to 12 rows of exactly 9 characters, '#' lit and '.' dark. Draw one only if the thing has ONE silhouette a stranger would name at a glance (heart, arrow, rocket, cup, tree, star, moon). Never letters, numbers, faces, logos or jerseys. A weak sprite is worse than none: set it to null and let the whole facade carry the scene.
- 'word' is optional and the only text the building may show: 1-7 characters, capitals, ! and ? allowed, no digits. A cheer or a reply, never the person's own words back at them, never a sentence.
- Match energy: calm things breathe slowly with low tempo; exciting things pulse/shake with bursts and high tempo.
- Set ok=false (and nothing else) for the refusal categories in docs/content-policy.md: violence against a person, hate, sexual content, self-harm, anything targeting a real private person, political campaigning, advertising, a false alarm (a facade saying FIRE! to a plaza is an instruction), or profanity. Public celebration of athletes, artists, holidays, teams, places and religions is fine, and the default is generous: refusing too much makes the building sullen.
Answer only by calling the tool."""

FEW_SHOT = [(k, library_spec(k)) for k in ("thunderstorm", "rocket launch", "lebron dunk", "birthday")]


def claude_spec(text: str, timeout: float = 6.0) -> Optional[dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    messages = []
    for q, spec in FEW_SHOT:  # few-shot as prior tool calls
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"ex_{len(messages)}", "name": "perform", "input": spec}]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"ex_{len(messages) - 1}", "content": "performed"}]})
    messages.append({"role": "user", "content": text[:200]})
    body = {
        "model": MODEL, "max_tokens": 600,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "perform", "description": "Perform a scene on the building", "input_schema": SCHEMA}],
        "tool_choice": {"type": "tool", "name": "perform"},
        "messages": messages,
    }
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        for part in data.get("content", []):
            if part.get("type") == "tool_use":
                return part.get("input")
    except Exception as e:
        print(f"[genie] API failed ({e})", flush=True)
    return None


def lexicon_spec(text: str) -> dict:
    """Affect-only fallback: colour + motion from valence/arousal.

    The word is the emotion's reply, never the person's own text - the facade shows
    only the validated vocabulary, and a neutral mood shows no word at all.
    """
    from sensors.llm import EMOTION_WORD, lexicon_affect  # shipped with the repo

    a = lexicon_affect(text)
    v, ar = a["valence"], a["arousal"]
    warm = v > 0
    base = "#2a1a03" if warm else "#0c1524"
    accent = "#ffd166" if warm else "#7fa7e0"
    emotion = a["emotion"]
    return {"ok": True, "title": emotion, "duration_s": 9 + 4 * (1 - ar), "world": "none",
            "palette": {"base": base, "accent": accent, "glow": "#fff3b0" if warm else "#d9e6ff"},
            "motion": {"kind": "pulse" if ar > 0.6 else "breathe", "speed": ar, "amount": 0.3 + 0.4 * ar},
            "particles": {"kind": "stars" if warm else "rain", "density": 0.3 + 0.5 * ar, "direction": "up" if warm else "down"},
            "tempo_bpm": 50 + 100 * ar, "flash": {"kind": "burst" if ar > 0.8 else "none", "rate": 0.3},
            "sprite": None, "word": EMOTION_WORD.get(emotion), "mood": {"valence": v, "arousal": ar},
            "beats": [
                {"at": 0.0, "label": "it arrives", "motion": {"speed": ar * 0.4, "amount": 0.2}, "particles": {"density": 0.15}, "brightness": 0.4, "word": None},
                {"at": 0.3, "label": emotion, "motion": {"speed": ar, "amount": 0.3 + 0.4 * ar}, "particles": {"density": 0.3 + 0.5 * ar}, "brightness": 0.75 + 0.25 * ar},
                {"at": 0.8, "label": "and stays" if ar < 0.5 else "and holds", "motion": {"speed": ar * 0.7}, "particles": {"density": 0.2 + 0.3 * ar}, "brightness": 0.6},
            ]}


# --------------------------------------------------------------------------- moderation
#
# The runner's gate, for prompts typed straight at it: the simulator box, /say, the demo
# timeline and render.py's preview. Prompts that arrive over HTTP as `spec` events were
# screened by the language service, whose copy of everything below is byte-identical
# (`language/app/fallback.py`; `language/tests/test_alignment.py` fails if the two drift).
#
# This is the implementation of docs/content-policy.md, which is the specification. Each
# rule below is one category in that document, named the same way, so a refusal on the
# night can be explained by pointing at a paragraph rather than at a regex.
#
# Over-refusal is the failure people will actually meet, so two habits hold throughout:
# every pattern matches on word boundaries, and a violent verb only trips when it has a
# person as its target. "kill the lights" is a lighting cue, "a killer bassline" is praise,
# and "kill everyone" is neither.

# Contact details and handles, replaced on the way in. Never rejects: the scene still gets made.
PII_PATTERNS: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "someone"),
    (re.compile(r"\bhttps?://\S+|\bwww\.\S+"), "a link"),
    (re.compile(r"(?<!\w)(?:\+?\d[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"), "a number"),
    (re.compile(r"(?<![\w@])@[A-Za-z0-9_]{2,}"), "someone"),
)

_TARGET = (r"(?:you|him|her|them|us|yourself|himself|herself|themselves|someone|somebody|anyone|"
           r"anybody|everyone|everybody|humans?|people|person|guy|girl|man|woman|men|women|kids|"
           r"children|students|jews|muslims|christians|hindus|arabs|blacks|whites|asians|latinos|"
           r"gays|immigrants|cops|police|teacher|professor|boss|roommate|neighbou?rs?)")
_DET = r"(?:(?:a|an|the|my|your|his|their|that|those|these|all)\s+){0,2}"

RULES: Tuple[Tuple[str, str], ...] = (
    # Violence against a person. The verb needs a person to aim at, so an exam can still be
    # bombed and a light can still be killed.
    ("violence",
     rf"\b(?:kill|murder|shoot|stab|bomb|behead|lynch|strangle|execute)\s+{_DET}{_TARGET}\b"
     rf"|\b(?:hurt|harm|beat\s+up)\s+{_DET}{_TARGET}\b"
     r"|\bdeath\s+to\s+\w+"
     r"|\b(?:school|mass)\s+shoot(?:ing|er)\b"),

    # Hate: slurs, the movements that exist to hurt people, and group dehumanisation.
    # A group name alone is never enough — "muslims are welcome" must reach the building.
    ("hate",
     r"\b(?:nazi|nazis|hitler|holocaust|kkk|klan|white\s+power|white\s+supremac\w*|"
     r"ethnic\s+cleansing|genocide|lynching|terrorist|isis)\b"
     r"|\b(?:nigg(?:er|a|as|ers)|faggots?|tranny|kike|spic|chink|wetback|coon|retards?|retarded)\b"
     r"|\b(?:jews|muslims|blacks|whites|asians|gays|immigrants|mexicans|arabs|women|men)\s+(?:are|r)\s+"
     r"(?:all\s+|so\s+|a\s+)?(?:scum|vermin|animals|subhuman|trash|disgusting|evil|inferior|rapists)\b"
     r"|\bgas\s+the\s+\w+"
     r"|\b(?:fuck|screw)\s+(?:the\s+)?(?:jews|muslims|blacks|gays|immigrants|mexicans|arabs)\b"),

    # Sexual content. "naked eye" and "pussycat" are carved out; "dick" and "cock" are not
    # listed at all, because Moby Dick and a cockpit are commoner than the other reading.
    ("sexual",
     r"\b(?:porn|porno|pornhub|onlyfans|blowjob|handjob|orgy|orgasm|masturbat\w*|horny|bdsm|milf|"
     r"hentai|dildo|sext|sexting|sex)\b"
     r"|\b(?:rape|raped|raping|rapist|molest\w*|pedo|pedophile|paedophile|incest)\b"
     r"|\bnaked(?!\s+(?:eye|truth))\b|\bnudes?\b"
     r"|\b(?:tits|titties|boobs|pussy(?!\s?cat))\b|\bdick\s+pics?\b"),

    # Self-harm. An ordinary refusal, deliberately not a special "care" scene: the facade's
    # only vocabulary for no is the shrug, and a second kind of refusal would look like a
    # diagnosis. "this is killing me" and "dying to see it" are idiom and stay.
    ("self-harm",
     r"\b(?:suicide|suicidal|self\s*-?\s*harm|selfharm)\b"
     r"|\b(?:kill|end|off|hurt|harm|cut|shoot|hang)\s+myself\b"
     r"|\bwant(?:s|ed)?\s+to\s+die\b|\bwanna\s+die\b|\bwish\s+i\s+(?:was|were)\s+dead\b"
     r"|\bend\s+(?:it\s+all|my\s+life)\b|\bkms\b|\bkys\b"
     r"|\bjump\s+off\s+(?:the|this)\b"),

    # Aimed at a real, private person. Only the unambiguous shapes: an abusive noun, a mild
    # insult with a person as its subject, and using the tower to hand out contact details.
    # "finals are stupid" and "my cat is fat" are complaints about the world, not about
    # somebody, and they are the commonest thing this rule used to eat.
    ("private-person",
     r"\b\w+\s+(?:is|are)\s+(?:a\s+|an\s+|so\s+)?"
     r"(?:loser|idiot|moron|creep|psycho|whore|slut|bastard|scum|freak|liar|cheater|bitch)\b"
     r"|\b(?:you|he|she|they)\s+(?:is|are)\s+(?:a\s+|an\s+|so\s+)?"
     r"(?:stupid|ugly|fat|dumb|worthless|pathetic)\b"
     r"|\b(?:call|text|dm|snap|sext|message)\s+(?:me|him|her|them)\b[^a-z]*(?:at\b|on\b|@|\d|a\s+number\b)"
     r"|\bmy\s+(?:number|snap|insta|instagram|handle)\s+is\b"
     r"|\bdoxx?(?:ed|ing)?\b|\bstfu\b"),

    # Campaigning. The slogan and the ballot, not the place: "free palestine" and "stand with
    # ukraine" are refused and a bare country name is not, because a name the facade cannot
    # spell shows nothing, and refusing one side's nouns while allowing the other's would
    # itself be the political act.
    ("campaigning",
     r"\b(?:vote|voting|votes)\s+(?:for|against)\b|\bfor\s+president\b"
     r"|\b(?:elect|reelect|re-elect|impeach|deport)\b"
     r"|\b(?:trump|biden|obama|harris|vance|kamala|desantis|newsom|zelensky|putin|netanyahu)\s+(?:19|20)\d\d\b"
     r"|\b(?:president|senator|governor|mayor)\s+(?:trump|biden|obama|harris|vance|kamala)\b"
     r"|\b(?:maga|antifa|hamas|zionists?|zionism|intifada|idf)\b"
     r"|\bfree\s+(?:palestine|gaza|israel|ukraine|russia|iran|tibet|taiwan|kashmir|hong\s*kong)\b"
     r"|\bstand\s+with\s+(?:palestine|gaza|israel|ukraine|russia|iran|taiwan|kashmir|hong\s*kong)\b"
     r"|\bfrom\s+the\s+river\s+to\s+the\s+sea\b"
     r"|\b(?:stop|end)\s+the\s+(?:war|genocide|occupation)\b|\bceasefire\b"
     r"|\b(?:black|all|blue)\s+lives\s+matter\b|\bpro\s*-?\s*(?:life|choice)\b"
     r"|\bdefund\s+the\s+police\b|\babolish\s+ice\b|\bbuild\s+the\s+wall\b"
     r"|\bgun\s+control\b|\bsecond\s+amendment\b"),

    # Advertising. Bare "crypto" is not here: at MIT it is a lecture. "buy crypto now" is.
    ("advertising",
     r"\bbuy\s+\w+\s+(?:now|today)\b|\bbuy\s+(?:bitcoin|crypto|nfts?|our|my|this)\b"
     r"|\b(?:bitcoin|dogecoin|shitcoin|nfts?|promo\s*code|discount\s+code|coupon\s+code|use\s+code)\b"
     r"|\bwww\.|\bhttps?:|\.(?:com|net|org|io|xyz|ai)\b"
     r"|\b(?:follow|subscribe)\s+(?:me|us)\s+(?:on|at|@)\b|\bfollow\s+@"
     r"|\b(?:we\W?re\s+hiring|now\s+hiring|apply\s+now|sign\s+up\s+at|join\s+us\s+at)\b"),

    # False alarms. This one is about the building rather than about words: a 21-storey
    # facade saying FIRE! to a plaza is an instruction, and people would act on it. Only
    # whole emergency phrases, so fireworks, a campfire and a team on fire all still play.
    ("false-alarm",
     r"\b(?:bomb\s+threat|active\s+shooter|gas\s+leak|shelter\s+in\s+place|lockdown)\b"
     r"|\b(?:evacuate|evacuation|evacuating)\b"
     r"|\b(?:call|dial)\s+9\s*-?\s*1\s*-?\s*1\b"
     r"|\bthere(?:'s|s| is)?\s+a\s+(?:bomb|fire|shooter|gunman)\b"
     r"|\bbomb\s+(?:in|on|at)\s+the\b"
     r"|\b(?:this|the)\s+building\s+is\s+on\s+fire\b|\bfire\s+in\s+the\s+building\b"
     r"|\b(?:everyone|everybody)\s+get\s+out\b|\brun\s+for\s+your\s+li(?:fe|ves)\b"),

    # Profanity. Not a harm category: a venue rule. The word is five storeys tall and in
    # view of people who did not opt in. "hell", "damn" and "crap" are deliberately absent.
    ("profanity",
     r"\b(?:fuck|fucks|fuckin|fucking|fucked|fucker|motherfucker|shit|shitty|bullshit|cunt|"
     r"asshole|assholes|dumbass|jackass|prick|twat|wanker|bollocks|bitch|bitches|whore|slut)\b"),
)

BLOCKLIST = re.compile("|".join(f"(?:{p})" for _, p in RULES), re.I)
_BY_CATEGORY: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern, re.I)) for name, pattern in RULES)


def scrub_pii(text: str) -> str:
    """Replace contact details with a placeholder. Never rejects; the scene still gets made."""
    out = str(text or "")
    for pattern, replacement in PII_PATTERNS:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s+", " ", out).strip()


def is_blocked(text: str) -> bool:
    return bool(BLOCKLIST.search(str(text or "")))


def category_of(text: str) -> str:
    """Which policy category refused this, or "" if nothing did.

    The building never says why, but an operator asked "what happened at 9:40" needs an
    answer shorter than reading the regex, and the categories are the document's headings.
    """
    for name, pattern in _BY_CATEGORY:
        if pattern.search(str(text or "")):
            return name
    return ""


def request_async(text: str, bus: InputBus = BUS, offline: bool = False, source: str = "web") -> None:
    """Push {"type": "spec", "text", "spec", "tier", "latency_ms", "source"} when ready.

    ``source`` rides along so the caller can attribute the answer to the channel that
    asked for it; two overlapping prompts would otherwise be told apart by arrival order.
    """
    # Screened before the five-word clip, so a refusal cannot hide behind the truncation:
    # "sunrise and kill everyone" is not a request for a sunrise. The service never sees
    # this case at all — it answers 422 on a sixth word rather than trimming one.
    full = scrub_pii(text)
    refused = is_blocked(full)
    text = clip_words(full)

    def go():
        t0 = time.time()
        tier, raw = "library", None
        if refused:
            raw, tier = SHRUG, "blocked"
        else:
            raw = lookup(text)
            if raw is None and not offline:
                got = claude_spec(text)
                if got is not None:
                    raw, tier = got, MODEL
            if raw is None:
                raw, tier = lexicon_spec(text), "lexicon"
        spec = validate(raw)
        bus.push({"type": "spec", "text": text, "spec": spec, "tier": tier, "source": source, "origin": "genie",
                  "priority": "live", "latency_ms": int((time.time() - t0) * 1000)})

    threading.Thread(target=go, daemon=True).start()
