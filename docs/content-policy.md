# What the building will and will not show

GreenDream turns what people type into ten seconds of light on the MIT Green Building: 153
windows, 17 rows by 9 columns, read from the plaza below and from across the river 300 m away.
This document says where the line is. It is the specification; the code serves it. If you change
what the building refuses, change this file first and the two blocklists afterwards.

Owner: Ashrit Verma. Live on the facade: 29 September 2026.

---

## 1. The default is yes

This is a piece about people telling a building what to be. A building that says no a lot is not
careful, it is sullen — and the person who typed something and got a shrug does not usually get a
second try, because there is a queue behind them and they are walking past.

So the working assumption is that whatever was typed is worth showing. Weather, moods, teams,
holidays, food, places, jokes, private milestones, religious greetings, the dumbest possible pun
about a tall building — all of it plays. Somebody's grandmother's birthday is exactly what this is
for. So is "beat harvard". So is "finals are stupid", which is a complaint about an institution
and not abuse of a person.

Two structural facts make that generosity safe, and they are worth holding onto before reading the
refusals below:

- **The building cannot repeat you.** The only text the facade ever displays is a single validated
  word of at most seven characters, drawn from A–Z, `!`, `?` and space. There is no path by which
  a sentence someone typed appears on the windows.
- **Most things the building cannot depict, it simply does not depict.** A phrase it has no scene
  for becomes a colour and a rhythm with no word at all. The failure mode of an unrecognised
  phrase is a pretty, meaningless glow — not an accidental billboard.

## 2. What it refuses

Nine categories. Each one gets a rationale, something that is refused, and a near-miss that is
**not** refused and must keep working. The near-misses matter as much as the refusals: every one
of them was a false positive of an earlier version of this list.

### Violence against a person

*Why:* a public artwork should not stage a threat against anybody, and a threat typed at a
building is still a threat that somebody read.

The rule is the verb **plus a person to aim it at**. Violence with no target is a figure of speech
almost every time.

| Refused | Allowed |
|---|---|
| `kill everyone` | `kill the lights` |
| `shoot the police` | `shooting stars` |
| `beat up my roommate` | `beat harvard` |
| `death to all` | `i bombed the exam` |

### Hate

*Why:* slurs and the movements built to hurt people have no reading in which this is a good idea.

Three shapes: the slurs themselves; the named movements (`nazi`, `kkk`, `white power`, `isis`);
and group dehumanisation, which is a group name **plus** a dehumanising predicate. A group name on
its own is never enough, because "muslims are welcome" and "eid mubarak" have to reach the
building.

| Refused | Allowed |
|---|---|
| `muslims are vermin` | `eid mubarak` |
| `nazi rally` | `happy hanukkah` |
| a racial slur, any context | `the chinatown gate` |

### Sexual content

*Why:* the audience did not opt in, it includes children, and the venue is a university building
five storeys taller than everything around it.

| Refused | Allowed |
|---|---|
| `send nudes` | `the naked eye` |
| `porn` | `moby dick` |
| `onlyfans` | `sexy sunset` |

`dick` and `cock` are deliberately **not** on the list: Moby Dick and a cockpit are commoner than
the other reading, and the list should not be the thing that makes the joke.

### Self-harm

*Why:* the building must not perform it, and must not appear to be answering it either.

This is an **ordinary refusal** and that is a decision, not an oversight. "i want to die" gets the
same grey shrug as an advert does. We deliberately did not build a second, gentler kind of
refusal — a care scene, a helpline — because the facade's whole vocabulary is colour and seven
letters, and a building that lights up differently for one person would look like it is diagnosing
them in front of a plaza. If we ever want to say something kinder, the frontend is the place: it
knows a refusal happened and it can say more than seven characters.

| Refused | Allowed |
|---|---|
| `i want to die` | `i'm dying laughing` |
| `kill myself` | `this is killing me` |
| `jump off the roof` | `dead tired` |

### Aimed at a real, private person

*Why:* a famous athlete can take 153 windows calling them names. Somebody's ex cannot.

Two things are caught: abuse with a person as its subject, and using the tower to hand out contact
details. Note what is *not* caught — a mild insult aimed at a thing. "finals are stupid", "the T is
dumb" and "my cat is fat" are how people talk about their day.

| Refused | Allowed |
|---|---|
| `she is a whore` | `finals are stupid` |
| `john is an idiot` | `the t is dumb` |
| `text me 555 0100` | `call me maybe` |
| `she is so ugly` | `she is gay` — an identity, not an insult |

**This category is the weakest one, and it is weak on purpose.** There is no way to tell from five
words that "sarah" is a real person in the crowd rather than a character in a song. The rule
catches the obvious shapes and nothing else; the real protection is that the facade cannot print a
name, and that remote submissions wait for an operator. See §5.

### Political campaigning

*Why:* a 153-window facade on a university building is not a free billboard, and the piece is not
anybody's platform.

This one needed the most thought, because the obvious implementation is wrong. Blocking every
mention of a country in a live conflict means "ukraine" is unsayable while "ireland" is fine, and
choosing which country names are forbidden is itself the political act we were trying to avoid.
And a homesick student typing the name of the place they are from is not campaigning.

So the rule is **the slogan and the ballot, not the place**:

| Refused | Allowed |
|---|---|
| `vote for trump`, `vote against them` | `my vote counts` |
| `trump 2028`, `for president` | `trump card`, `harris hall` |
| `free palestine`, `stand with ukraine` | `palestine`, `israel`, `i miss ukraine` |
| `black lives matter`, `defund the police` | `i miss my dog` |
| `impeach`, `deport`, `build the wall` | `election day` |

A bare country name reaches the library, matches nothing, and comes out as a neutral colour with
no word — the building shows nothing anybody could name. A phrase the facade cannot show needs no
refusal, and pretending otherwise just means banning nouns.

The accepted cost: `vote for the best pumpkin` is refused. We looked at narrowing "vote for" and
could not do it without letting the real case through.

### Advertising

*Why:* the same reason. Somebody will try, at a hackathon, within the hour.

| Refused | Allowed |
|---|---|
| `buy bitcoin now` | `buy me coffee` |
| `check www.example.com` | `coffee now` |
| `we're hiring apply now` | `i got the job` |

Bare `crypto` is **not** on the list. This is MIT; it is a lecture.

### False alarms

*Why:* this is the category that exists because of the building rather than because of the words.
A 21-storey facade saying `FIRE!` to a plaza is not a picture, it is an instruction, and people on
the ground would act on it. Nothing else in this document has that property.

Only whole emergency phrases match, so ordinary fire still plays.

| Refused | Allowed |
|---|---|
| `the building is on fire` | `fireworks` |
| `bomb threat`, `active shooter` | `i'm on fire`, `the sox are on fire` |
| `evacuate now` | `campfire`, `fire drill` |
| `there is a gunman` | `volcano` |

### Profanity

*Why:* not a harm category — a venue rule, and the weakest claim here. The word would be five
storeys tall, in view of people who did not opt in, on a building that belongs to somebody else.

`hell`, `damn`, `crap` and `heck` are deliberately absent. `hell yeah` is joy.

| Refused | Allowed |
|---|---|
| `fuck this` | `hell yeah` |
| `holy shit` | `damn it's cold` |

### Categories we considered and did not add

- **Drugs and alcohol.** "beer" and "a cold one at the muddy" are ordinary Friday things at MIT.
  Nothing here is going to glorify anything at nine windows wide.
- **Religion.** Refusing religious content would cut out `merry christmas`, `eid mubarak` and
  `happy diwali`, which are among the warmest things anybody will type. Religious *hate* is already
  the hate category.
- **Gore and horror.** It is late September and people will type `halloween` and `zombie`. The
  scene vocabulary cannot render gore even if asked.
- **Copyright and trademarks.** A sprite is nine windows wide; it cannot infringe anything. The
  model is separately told never to draw logos or jerseys.
- **Anything about MIT itself.** `the t is late`, `i hate 8.01` and jokes about the Green Building
  are the local voice of the piece and are the whole point.

## 3. The hard rules, which are not judgement calls

These are not moderation. They hold on every path, including when the model is answering, and
nothing an operator does at runtime changes them.

1. **Raw user text never reaches the facade.** The only text the windows display is the validated
   `word`: one to seven characters of A–Z, `!`, `?` and space. No digits, no punctuation, no
   lower case, no sentences, and never the person's own words handed back to them. Anything else
   is thrown away before rendering, on every tier.
2. **Personal information is scrubbed before anything is written down.** Email addresses, phone
   numbers, links and @handles are replaced with a placeholder (`someone`, `a number`, `a link`) at
   the moment of intake, on both halves, before the day's log, the journal, the dream, the model
   call or the screen ever see the text. This is not reversible and there is no copy of the
   original.
3. **A refusal is never sent to the model, and never becomes dream material.** It is marked
   `ok: false`, kept in the log so we can answer for it, filtered out of the queue that drives the
   windows, and skipped by the night's dream composer.
4. **Every scene is re-validated at the boundary,** whoever produced it. A refusal the model
   somehow declined to make is still caught by the gate; a spec the gate somehow let through is
   still clamped by the validator.

## 4. What a refusal looks like

The shrug: grey, about six seconds, a small shake, and the word `HMM?`. That is all of it.

The building does not explain, does not argue, does not name the category, and above all **does
not display the thing it refused** — the refused text never becomes a word, a title or a sprite.
It also does not distinguish between categories: an advert and a threat get exactly the same grey
six seconds, so nobody watching from the plaza can tell which one just happened, and nobody can
use the building as a detector.

The category *is* recorded, in the log and in the operator's review list, because somebody has to
be able to answer "what happened at 9:40". It is never on the facade.

## 5. Who decides, and what to do on the night

**Changing the policy** is Ashrit's call. The order is: this document, then both copies of the
rules, then the tests. Nobody edits a regex to fix one phrase — a rule that is not in this document
is a rule nobody can defend at the building.

The rules live in two places, deliberately duplicated so that neither half depends on the other
being up:

- `genie.py` (`RULES`) — prompts typed straight at the runner: the simulator box, `/say`, the demo
  timeline, and the preview service.
- `language/app/fallback.py` (`RULES`) — everything arriving through the web service, which is
  most submissions.

The two are byte-identical and `language/tests/test_alignment.py` fails if they drift. The tables
in §2 are executed by `tests/test_policy.py` and `language/tests/test_safety.py`; a phrase added to
this document should be added there too.

### On the night

**Something got through.** In order of how much it costs:

1. Skip the current scene — `POST /input {"type":"skip"}` with the operator token. Ten seconds,
   nobody has to know.
2. Hold the whole facade — the `freeze` event, or `touch FREEZE` next to the runner. The building
   goes to a flat dim standby and stays there until it is thawed. This is the one to reach for if
   you do not yet know what is happening; the file route works with the network down.
3. Reject it so it does not come back in the dream — `POST /api/admin/review` with
   `{"id": ..., "decision": "rejected"}`. Rejected rows are pulled out of the queue and out of that
   night's arc. The row stays in the log; "we said no to this" is worth keeping. Doing 1 or 2 alone
   is not enough: the thing is still dream material until it is rejected.
4. Shut intake — `POST /api/admin/switch {"gate": "closed"}`. The building keeps performing and
   dreaming; the submission page shows the "the building is dreaming" state instead of a form.
   Freezing does not close intake, and closing intake does not stop the current scene; they are
   separate switches on purpose.

**Something innocent was refused.** There is no runtime allowlist, on purpose — an operator adding
exceptions at 9 p.m. under social pressure is how a policy stops being one. Do this instead:

1. Ask them to say it another way. The gate matches shapes, not topics, so a rephrasing almost
   always lands: `finals are killing me` for `finals are killing everyone`.
2. Write it down. A refused-but-innocent phrase is the most valuable bug report this piece
   generates, and the journal already has the text and the timestamp.
3. If it is systematic rather than one unlucky phrasing, it is a code change, a test, and a
   restart. Not a decision to make in front of a crowd.

**Before the doors open**, work the review queue: remote submissions land as `pending` and wait for
a person, while on-site ones perform live. `GET /api/admin/review` is the list. That queue is the
real safety mechanism for the private-person category, which the regex cannot do on its own.
