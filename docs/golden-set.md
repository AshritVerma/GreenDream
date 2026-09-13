# The golden set: what forty real phrases do to the library

Run it yourself:

    python language/tools/golden_set.py            # the report
    python language/tools/golden_set.py --misses   # only the rows that disappointed

Offline, no key, no server. It calls the local tier directly — the one that answers on the
night whenever the model is off, unreachable or slow, and therefore the floor under the
piece. The forty phrases are in `language/tools/golden_set.py`; they are what somebody
standing on that plaza on the evening of 29 September is likely to type: the weather that
week, the teams playing, the things this building in particular makes people think of, the
holidays near the date, the jokes, and a few that are genuinely hard. Four are there to be
refused and twelve to miss the library on purpose, so every tier gets exercised.

## What came back

    tiers      blocked 4   lexicon 12   library 24
    as wanted  32/40
    library coverage  20/33 scenes reached by a phrase in this set, 33/33 by some phrasing
    recognizability   mean 3.58 over 36 rated — all 36 read off a spec at a desk, none confirmed

**The 33 scenes are sound, and they are all reachable.** No scene is stranded: the thirteen
the forty never touch (`a tree`, `calm ocean`, `city lights`, `coffee`, `go up`, `good luck`,
`graduation`, `lebron dunk`, `northern lights`, `rocket launch`, `take me to space`,
`the forest`, `volcano`) are each reached by one plain phrasing — "the ocean", "the woods",
"wish me luck", "a rocket launch". They are scenes nobody happens to ask for in late
September, not scenes nobody can ask for. That is a real result: the previous worry was
that the library advertised things no phrasing could get to, and it does not.

**The failures are holes, not errors.** Every one of the eight findings is the same shape —
a thing people will obviously say, no scene for it, a flat mood instead:

| phrase | what happens | why it matters |
| --- | --- | --- |
| `go pats` | lexicon, grey | the last Sunday in September is football; Sox, Celtics and Bruins all have scenes |
| `first day of fall` | lexicon, grey | no autumn scene at all, while snow, Christmas and midsummer are covered |
| `the t is late` | lexicon, grey | the most Boston sentence there is |
| `play tetris` | lexicon, grey | this is *the Green Building*; somebody will ask within ten minutes |
| `the great dome` | lexicon, grey | a dome is one of the few silhouettes that works at nine wide |
| `a windy night` | lexicon, grey | the commonest thing to say about a night on that plaza |
| `beat harvard` | lexicon, grey | the local joke, and it is not really about sport |
| `foggy morning` | *sunrise* | "morning" drags it somewhere brighter and quite different |

## Recognizability, and why the number is not a measurement

The only question that matters is *would a stranger 300 m away name what they are seeing?*
Nothing in the harness can answer it. The `rec` column it prints is arithmetic over how much
of the query the matcher consumed — it says the words were understood, not that the building
was. So each phrase carries a rating (1–5) **plus who made it**: `desk` (read off the scene
spec at a keyboard), `plaza`, or `river`. The footer counts them loudly.

Right now all 36 ratings are `desk` and none are confirmed. **Treat 3.58 as a hypothesis
about the building, not a fact about it, and do a plaza pass before the 29th.** The desk
ratings are blind to exactly the thing that will decide the night: what nine windows of
orange actually look like from the Mass Ave bridge. The places they are most likely to be
wrong are the sprite-dependent scenes — the ring in *she said yes*, the smile in
*i'm so happy*, the cake in *birthday* — which are rated on the word carrying them.

## Fixed, because they were not taste calls

Two matcher bugs, both of which made the building *confidently* wrong, which is worse than
a miss. Both are pinned by tests (`tests/test_library.py`, `language/tests/test_golden_set.py`).

1. **A colour no longer picks a scene.** Every scene has a palette, so a colour is the least
   discriminating word in the vocabulary, and whichever entry happened to list one won by
   accident of authorship. "red" reached *go sox*: "a red balloon" and "red leaves" both put
   GO SOX! on the facade, and "a gold medal" got BRUINS. Colours are now excluded from the
   derived index; an alias may still name one deliberately ("red sox", "golden hour").

2. **The typo pass no longer corrects ordinary English.** One wrong letter in a five-letter
   word scores exactly the 0.8 cutoff, so every short word had a neighbour in the index:
   "i am tired" → HIRED!, "shana tova" → *merry christmas* (santa), "the t is late" →
   *coffee* (latte), "a windy night" → *i'm so happy* (light). The pass now needs six
   letters, which still forgives the misspellings that actually happen — firewroks,
   chirstmas, brithday, graduaton, lightining — and stops inventing scenes out of words.

Sixteen aliases, all for scenes that already exist and were being missed by their most
likely phrasing. The worst of them: **`marry me` did not reach *she said yes***, the scene
whose entire subject it is. Also `dunkin` (went to *lebron dunk*; in this city it is
coffee), `sundown` (went to *snow day* on a fuzzy accident), `snowstorm`, `moonrise`,
`pouring`, `drizzle`, `milky way`, `the esplanade`, `fingers crossed`, `break a leg`,
`congrats`, `congratulations`, `boston`, `new year`, `happy new year`.

## Recommended, and deliberately not done

New scenes are authored art and a taste call, so they are written down rather than guessed
at. In priority order, with the argument for each:

1. **`go pats` / Patriots.** The cheapest gap on the list. Three Boston teams have scenes and
   the one playing that weekend does not. Navy and silver, a vertical surge; no sprite needed.
2. **Autumn.** `first day of fall`, `the leaves are changing`, `fall foliage` — late September
   in New England and there is no autumn scene, while there is snow, Christmas and midsummer.
   Aliases: `fall`, `autumn`, `foliage`, `leaves`.
3. **`play tetris`.** People played Tetris on these windows in 2012 and the piece will be read
   against that. A block falling down a 9-wide grid is native to this facade. `tetris.py`
   already exists at the root and is off limits to edit, but a *library scene* is separate:
   a few falling tetrominoes and a line clear, not a playable game.
4. **The T.** `the t is late`, `the red line`. A line of light that crawls up, stops, and does
   not arrive. Funny at 300 m and unmistakably local.
5. **Wind / fog.** `a windy night`, `foggy morning`. The sweep motion exists; fog is dim,
   still and diffused, which is the easiest thing on this list to render honestly. Until
   there is a fog scene, consider whether `morning` should alias to *sunrise* at all — it is
   what sends "foggy morning" somewhere bright.
6. **The Great Dome**, and **`beat harvard`** (crimson overwhelmed by something else). Both
   are MIT-specific and both are jokes the crowd will get; both are lower value than the above
   because they are narrower.

Also recommended, not done, because each is a judgement somebody else should make:

- **`yankees` → *go sox***. "yankees suck" is a Fenway staple and currently shows nothing.
  Left alone because it is a policy question (rivalry vs. targeting) more than a matcher one.
- **`rainbow` → *it's raining***, via whole-phrase fuzzy. A rainbow is arcs of colour and
  the rain scene is grey with an umbrella. Wants its own scene, or the fuzzy pass tightened.
- **`happy halloween`, `happy rosh hashanah` → *i'm so happy***, through the bare word
  "happy". Not wrong — warm and celebratory — but generic, and a smile sprite is an odd
  answer to a new year. Halloween is inside a month of the date.
- **Nothing to remove.** Every scene earns its place; the two weakest for this site are
  `lebron dunk` (a Philadelphia reference in Boston, oddly) and `volcano`, and even those are
  reachable and legible. Removing scenes is not where the value is.
