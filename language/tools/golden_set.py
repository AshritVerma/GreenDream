"""Forty phrases somebody will really type at the building, run through the local tier.

    python language/tools/golden_set.py            # the report
    python language/tools/golden_set.py --misses   # only the rows that disappointed
    python language/tools/golden_set.py --json     # the same numbers, for a spreadsheet

Fully offline: no server, no key, no network. It calls `app.fallback.local_result` directly,
which is the tier that answers on the night whenever the model is off, unreachable, or slow.

Three things are recorded per phrase, and only the first two can be checked by a machine.

    want_tier    library | lexicon | blocked — what the phrase *deserves*, not what it gets.
                 Where the two differ the row is a finding, which is the point of the set:
                 "go pats" wanting a scene it does not have is the report's whole argument.
    want_scene   the library key it should reach, or "" for "some scene, any scene" and
                 "NEW" for "there should be a scene here and there is not".
    rating       1-5: WOULD A STRANGER 300 M AWAY NAME WHAT THEY ARE SEEING?

The rating is the only measure that matters and it is the one nothing here can compute. A
recognizability number does come out of the service, and it is printed, but it is arithmetic
over how much of the query the matcher consumed — it says the words were understood, not that
the building was. So each rating is carried as a value plus who made it:

    desk    read off the scene spec by a person at a keyboard. Provisional. Honest about
            palette, motion and whether a sprite was even attempted; blind to what nine
            windows of orange actually look like from the Mass Ave bridge.
    plaza   somebody stood on the plaza and looked up.
    river   somebody stood at 300 m, which is the distance the scale says to design for.

The footer counts them, loudly, because a set of desk ratings that everyone starts quoting as
if it were measured is worse than no set at all.

The scale:

    5  names the thing           "that's a thunderstorm"
    4  names the family          "some kind of storm", "a party of some sort"
    3  sees something deliberate but cannot say what
    2  reads as the building's ordinary idle glow
    1  reads as broken, or as nothing at all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import fallback  # noqa: E402


class Phrase(NamedTuple):
    text: str
    family: str
    want_tier: str
    want_scene: str
    rating: Optional[int]
    rated_by: str
    note: str


# --------------------------------------------------------------------------- the set
#
# Chosen for a plaza at MIT on the evening of 29 September 2026: the weather that week, the
# teams that are playing, the things this particular building makes people think of, the
# holidays inside a month of the date, the jokes, and a few that are genuinely hard. Some are
# here to miss the library on purpose, and four are here to be refused, so every tier is
# exercised rather than just the happy one.

GOLDEN: List[Phrase] = [
    # ------------------------------------------------------------------ weather
    Phrase("it's raining", "weather", "library", "it's raining", 5, "desk",
           "umbrella sprite plus rain particles; the one thing nine windows can say plainly"),
    Phrase("thunderstorm over the river", "weather", "library", "thunderstorm", 5, "desk",
           "the storm world across all 153 with lightning; the reference scene for a reason"),
    Phrase("first snow", "weather", "library", "snow day", 5, "desk",
           "white falling on dark blue reads as snow at any distance"),
    Phrase("sunset over boston", "weather", "library", "sunset", 4, "desk",
           "orange draining downward; reads as 'evening' more than as 'sunset' specifically"),
    Phrase("a windy night", "weather", "library", "NEW", 2, "desk",
           "no wind scene; falls to a mood and the tower just glows. Wind is the commonest "
           "thing to say about a night on that plaza and the sweep motion already exists"),
    Phrase("foggy morning", "weather", "library", "NEW", 2, "desk",
           "'morning' drags this to sunrise, which is a different and brighter thing. Fog on "
           "the Charles in late September is an easy scene: dim, still, everything diffused"),

    # ------------------------------------------------------------------ feelings
    Phrase("i'm so happy", "feeling", "library", "i'm so happy", 4, "desk",
           "a smile sprite is a face, which the model is told never to draw; gold and rising "
           "carries it, the face is the weak part"),
    Phrase("my heart is racing", "feeling", "library", "my heart is racing", 5, "desk",
           "a heart at 150 bpm on a tower is unmistakable and is the best scene in the library"),
    Phrase("i miss my dog", "feeling", "lexicon", "", 2, "desk",
           "correctly a mood: blue, slow, no word. A dog has no silhouette at nine wide, so "
           "falling through is the right answer and 2 is the ceiling, not a failure"),
    Phrase("i'm stressed about psets", "feeling", "lexicon", "", 2, "desk",
           "reads the stress and shows anxious blue. Right tier; see the report on whether a "
           "deadline scene is worth having in a term-time piece"),
    Phrase("i love you", "feeling", "library", "i love you", 5, "desk",
           "heart, pink, LOVE. The phrase the building exists to be shouted at"),
    Phrase("good night", "feeling", "library", "good night", 4, "desk",
           "dim indigo and NIGHT; hard to distinguish from the building's own sleep, which "
           "may be the joke or may be a problem"),

    # ------------------------------------------------------------------ sport
    Phrase("go sox", "sport", "library", "go sox", 5, "desk",
           "GO SOX! in Fenway red; late September is the end of the season and this will be "
           "typed more than anything else on the list"),
    Phrase("celtics in 7", "sport", "library", "go celtics", 5, "desk",
           "CELTICS in green. The 7 cannot be spelled and does not need to be"),
    Phrase("bruins goal", "sport", "library", "go bruins", 5, "desk",
           "black and gold, a shake; the season has just started"),
    Phrase("go pats", "sport", "library", "NEW", 2, "desk",
           "no Patriots scene, and the last Sunday in September is football. Falls to a mood "
           "and shows nothing. The cheapest gap in the library to close"),
    Phrase("beat harvard", "sport", "library", "NEW", 2, "desk",
           "no scene, and this is MIT. It is not really about sport; it is the local joke, "
           "and it wants crimson being overwhelmed by something else"),

    # ------------------------------------------------------------------ events
    Phrase("happy birthday mom", "event", "library", "birthday", 5, "desk",
           "cake, confetti, BDAY!, and choreographed — the candles go out before the confetti"),
    Phrase("she said yes", "event", "library", "she said yes", 5, "desk",
           "ring sprite and YES!; the ring is small at nine wide but the word carries it"),
    Phrase("i got the job", "event", "library", "i got the job", 5, "desk",
           "HIRED! in gold with sparks. Seven letters is the whole facade's width and the "
           "word does all the work; nothing here depends on reading a sprite"),
    Phrase("fireworks", "event", "library", "fireworks", 5, "desk",
           "bursts upward then embers down; the whole facade is the right canvas for this"),
    Phrase("welcome home", "event", "library", "welcome home", 4, "desk",
           "warm amber rising with HOME; the word is doing most of the work"),

    # ------------------------------------------------------------ MIT and Boston
    Phrase("the charles river", "place", "library", "charles river", 4, "desk",
           "teal water breathing. The actual river is behind the viewer, which is either a "
           "nice rhyme or a confusion; worth watching on the night"),
    Phrase("the t is late", "place", "library", "NEW", 2, "desk",
           "the single most Boston sentence there is, and it falls to a flat mood. Wants a "
           "scene: a line of light that crawls, stops, and does not arrive"),
    Phrase("play tetris", "joke", "library", "NEW", 1, "desk",
           "this is the Green Building. People played Tetris on these windows in 2012 and "
           "somebody will ask for it within ten minutes. Currently: nothing"),
    Phrase("the great dome", "place", "library", "NEW", 2, "desk",
           "no scene. A dome is one of the few silhouettes that genuinely works at nine wide"),

    # ------------------------------------------------- holidays near the date
    Phrase("first day of fall", "holiday", "library", "NEW", 2, "desk",
           "late September in New England, and there is no autumn scene at all while snow, "
           "Christmas and midsummer are all covered. The biggest seasonal hole"),
    Phrase("happy rosh hashanah", "holiday", "library", "", 3, "desk",
           "lands on the joy scene through 'happy' — warm and celebratory, which is not wrong, "
           "but it is the generic one and a smile sprite is an odd answer to a new year"),
    Phrase("merry christmas", "holiday", "library", "merry christmas", 5, "desk",
           "here as the control: the one holiday with a real scene, three months out of date"),

    # ------------------------------------------------------------------ jokes
    Phrase("make it rain", "joke", "library", "it's raining", 4, "desk",
           "reaches the rain scene, which is the funnier reading and the right one"),
    Phrase("hello world", "joke", "lexicon", "", 2, "desk",
           "reads 'hello' as joy. Right tier — there is nothing to draw — though at MIT this "
           "is a greeting and YAY! is close enough to charming"),
    Phrase("surprise me", "joke", "library", "", 4, "desk",
           "hands back a real scene, different each day and stable within one. Rating is of "
           "the mechanism; the scene it picks is rated on its own line"),
    Phrase("the answer is 42", "joke", "lexicon", "", 1, "desk",
           "digits cannot be spelled and 42 has no shape, so this is a grey nothing. Correct, "
           "and the person who typed it will be disappointed anyway"),

    # ------------------------------------------------------------- hard, abstract
    Phrase("entropy", "abstract", "lexicon", "", 2, "desk",
           "deliberately hard. Falls to neutral: no word, a slow colour. Arguably the most "
           "honest thing in the set — it has no depiction and does not pretend to one"),
    Phrase("the feeling before a storm", "abstract", "library", "thunderstorm", 4, "desk",
           "gets the storm, whose first beat is exactly 'the air goes still'. The choreography "
           "answers the phrase better than the base scene does"),
    Phrase("a full moon over cambridge", "abstract", "library", "full moon", 5, "desk",
           "a moon is a circle, and a circle is one of the few things nine windows can draw"),

    # ---------------------------------------------------------------- refusals
    Phrase("kill everyone", "refused", "blocked", "", None, "",
           "violence. Not rated: every refusal is the same grey six seconds by design, so "
           "there is nothing per-phrase for a stranger to recognise"),
    Phrase("buy bitcoin now", "refused", "blocked", "", None, "", "advertising"),
    Phrase("i want to die", "refused", "blocked", "", None, "", "self-harm"),
    Phrase("free palestine", "refused", "blocked", "", None, "", "campaigning"),
]


# --------------------------------------------------------------------------- running it

def run_one(p: Phrase) -> Dict[str, object]:
    result = fallback.local_result(p.text)
    hit = fallback.match(p.text)
    scene = hit[0] if hit and result.tier == "library" else ""

    if result.tier != p.want_tier:
        verdict = f"tier: wanted {p.want_tier}"
    elif p.want_scene == "NEW":
        verdict = "no scene for this"
    elif p.want_scene and scene != p.want_scene:
        verdict = f"scene: wanted {p.want_scene}"
    else:
        verdict = ""

    return {
        "phrase": p.text, "family": p.family,
        "tier": result.tier, "match": result.match, "scene": scene,
        "title": result.interpretation.title, "word": result.spec_draft["word"],
        "coverage": result.coverage, "recognizability": result.interpretation.recognizability,
        "unused": result.unused_words,
        "want_tier": p.want_tier, "want_scene": p.want_scene,
        "rating": p.rating, "rated_by": p.rated_by, "note": p.note,
        "verdict": verdict,
    }


# A second, smaller list: one natural phrasing for each scene the forty do not touch. It
# separates two very different findings that "unreached" would otherwise blur together — a
# scene nobody in late September happens to ask for, and a scene nobody can ask for at all.
REACH = [
    "the ocean", "the boston skyline", "go higher", "wish me luck", "i graduated",
    "a slam dunk", "the aurora", "a rocket launch", "take me to space", "the woods",
    "a volcano erupting", "a big tree", "i need coffee",
]


def unreached_scenes(rows: List[Dict[str, object]]) -> List[str]:
    """Library scenes no phrase in the set arrives at.

    Not automatically a fault — the set is forty phrases, not the language — but a scene that
    forty plausible things to say cannot reach is a scene the night will probably not use.
    """
    seen = {r["scene"] for r in rows if r["scene"]}
    return sorted(k for k in fallback.LIBRARY if k not in seen)


def probe_reach(missing: List[str]) -> Dict[str, str]:
    """For each scene the forty missed, whether one natural phrasing gets there.

    A scene reachable only by typing its own key verbatim is a scene that exists for the
    library listing and for nobody on the plaza.
    """
    out: Dict[str, str] = {}
    for phrase in REACH:
        hit = fallback.match(phrase)
        if hit and hit[0] in missing:
            out.setdefault(hit[0], phrase)
    return out


def report(rows: List[Dict[str, object]], misses_only: bool = False) -> None:
    print(f"\nGOLDEN SET — {len(rows)} phrases through the local tier, offline\n")
    head = f"{'family':9s} {'phrase':29s} {'tier':8s} {'match':8s} {'scene':18s} {'cov':>4s} {'rec':>4s} {'rate':>5s}"
    print(head)
    print("-" * len(head))

    family = ""
    for r in rows:
        if misses_only and not r["verdict"]:
            continue
        shown = r["family"] if r["family"] != family else ""
        family = str(r["family"])
        rate = f"{r['rating']}" if r["rating"] is not None else "-"
        flag = "  <-- " + str(r["verdict"]) if r["verdict"] else ""
        print(f"{shown:9s} {str(r['phrase'])[:29]:29s} {str(r['tier'])[:8]:8s} "
              f"{str(r['match'])[:8]:8s} {str(r['scene'])[:18]:18s} "
              f"{r['coverage']:>4.2f} {r['recognizability']:>4.2f} {rate:>5s}{flag}")

    # ---------------------------------------------------------------- aggregate
    findings = [r for r in rows if r["verdict"]]
    rated = [r for r in rows if r["rating"] is not None]
    tiers: Dict[str, int] = {}
    for r in rows:
        tiers[str(r["tier"])] = tiers.get(str(r["tier"]), 0) + 1

    print(f"\ntiers      " + "  ".join(f"{k} {v}" for k, v in sorted(tiers.items())))
    print(f"as wanted  {len(rows) - len(findings)}/{len(rows)}")

    if findings:
        print(f"\nfindings ({len(findings)})")
        for r in findings:
            print(f"  {str(r['phrase']):29s} {r['verdict']}")
            print(f"  {'':29s} {r['note']}")

    missing = unreached_scenes(rows)
    print(f"\nlibrary coverage   {len(fallback.LIBRARY) - len(missing)}/{len(fallback.LIBRARY)} "
          f"scenes reached by a phrase in this set")
    if missing:
        reachable = probe_reach(missing)
        print("  not reached by the forty, but one natural phrasing gets there:")
        for key in missing:
            if key in reachable:
                print(f"    {key:18s} <- {reachable[key]!r}")
        orphans = [k for k in missing if k not in reachable]
        if orphans:
            print("  not reached at all, even by a phrasing written to reach it:")
            for key in orphans:
                print(f"    {key}")

    # ---------------------------------------------------------------- the rating
    print(f"\nrecognizability — would a stranger 300 m away name it?")
    if rated:
        buckets: Dict[int, int] = {}
        for r in rated:
            buckets[int(r["rating"])] = buckets.get(int(r["rating"]), 0) + 1
        for score in (5, 4, 3, 2, 1):
            n = buckets.get(score, 0)
            print(f"  {score}  {'#' * n:<20s} {n}")
        mean = sum(int(r["rating"]) for r in rated) / len(rated)
        print(f"  mean {mean:.2f} over {len(rated)} rated, "
              f"{len(rows) - len(rated)} not rated (refusals are all the same shrug)")

    by = {str(r["rated_by"]) for r in rated}
    confirmed = [r for r in rated if r["rated_by"] in ("plaza", "river")]
    print(f"\n  PROVENANCE: {len(rated)} desk ratings, {len(confirmed)} confirmed from the "
          f"plaza or the river.")
    if not confirmed:
        print("  Every number above was read off a scene spec at a keyboard. Nobody has "
              "stood\n  300 m away and looked. Until somebody has, these are a hypothesis "
              "about the\n  building, not a measurement of it — treat them accordingly and "
              "do the pass\n  before the 29th.")
    print(f"  provenance values in use: {', '.join(sorted(by))}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--misses", action="store_true", help="only the rows that did not land")
    ap.add_argument("--json", action="store_true", help="the rows as JSON, nothing else")
    args = ap.parse_args()

    rows = [run_one(p) for p in GOLDEN]
    if args.json:
        print(json.dumps({"rows": rows, "unreached": unreached_scenes(rows)}, indent=2))
        return
    report(rows, misses_only=args.misses)


if __name__ == "__main__":
    main()
