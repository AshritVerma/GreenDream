# The face — implementation plan

The building gets a face: two eyes with moving pupils, eyelids that blink, and a faint mouth. By
day the eyes are open and rest on whoever is on the ground below and on the traffic; the eyes are
calm and deliberate by design, not darting (§2.0). Through dusk the lids come down. **At night the
face is still there with its eyes closed, breathing with the body, with a slow bulge sliding under
the lids while it dreams** — it sleeps rather than disappearing. The only thing that removes the
face is a performance, which owns the whole facade while it plays.

Nothing is watching: there is no camera and there is not going to be one. The traffic below is a
seeded synthetic model — random-looking to anyone on the plaza, reproducible for demos and tests
— and that guess is the design rather than a placeholder (§3).

This is a plan, not a change. Nothing outside this file has been edited. Read `HANDOFF.md` §4
(event vocabulary), §6 (conventions) and §7 (decisions) first; this plan assumes all of them.

---

## 0. What replaces what

`GreenDream._idle_awake()` already draws two things: a breathing up-light from the base, and a
single bright blob it calls a "gaze" that eases toward random targets every 1.5–4 s. The blob is
the thing being replaced. The up-light stays exactly as it is and becomes the body: it is bright
at the base and dim at the top (its sigmoid is driven by `depth = RR / (ROWS - 1)`), which is
precisely the contrast the face needs, because the face lives in the dim rows at the top.

Three attributes disappear from `setup()` — `self.gaze`, `self.gaze_goal`, `self.wander_t` — and
become internals of a new `Face` class in a new module `face.py`.

---

## 1. Face geometry on 17 x 9

### 1.1 The aspect-ratio problem

The grid is 17 rows by 9 columns, but the windows are not square and neither is their pitch. The
Green Building's display facade is roughly 18–22 m wide and the 17 window rows span roughly
70–75 m, so the column pitch is about 2.4 m and the row pitch about 4.3 m. **One row is about
twice one column.** The whole grid is therefore about 9 units wide and 34 units tall — a ratio
near 1:3.8, not 1:1.9.

Everything below is derived from a single constant:

```python
CELL_ASPECT = 2.0     # row pitch / column pitch on the real facade
```

Consequences, which are the answer to "a naively proportioned face will look stretched":

- A face drawn to fill the grid would be four times too tall. The face uses **all 9 columns and
  only 7 rows** (rows 1–7). Physically that box is 9 wide by 14 tall, a ratio of 1:1.55, which is
  close to a human head (about 1:1.4). A face box of 9 x 12 rows, which is what "fill the top
  two-thirds" would suggest, would be 9 x 24 and would read as a totem, not a face.
- Feature spacing is chosen in physical units, then divided by `CELL_ASPECT` to get rows. Eye
  separation is 4 columns; a human face has eye-line-to-mouth distance about equal to eye
  separation, so the mouth sits 4 physical units below the eye line, which is `4 / 2.0 = 2` rows.
  Eye centre row 3.5, mouth row 6.4. Not 8 rows down, which is what it would be if rows were
  treated as square.
- Pupil travel is 0.85 columns horizontally and **0.45 rows** vertically, because
  `0.45 * 2.0 = 0.90 ≈ 0.85`. Equal physical excursion, unequal grid excursion.
- The pupil hole is a gaussian with sigma 0.60 columns and 0.80 rows. It is deliberately taller
  than wide in grid terms (physically 0.6 x 1.6) so that it spans the two-row socket and a
  vertical look is legible: "the dark cell moved from the top row to the bottom row" reads at
  300 m, whereas a round-in-grid-space hole would only ever dim one row slightly.

`CELL_ASPECT = 2.0` is the working value and is settled. It is estimated from the building's
proportions rather than measured, and it does not need to be exact — it only has to stop the face
being drawn four times too tall. If the facade turns out to be 1.6 or 2.6, the face reproportions
by editing that one constant and nothing else.

### 1.2 The layout

The face occupies rows 1–7. Rows 8–16 are the body and belong to the existing up-light. The face
never writes below row 7; a test asserts this.

```
             col 012345678
     row  0      .........   crown — stays dark (DUSK's lid enters here, DAWN's light exits here)
     row  1      .........   forehead
     row  2      .........   brow line — deliberately empty, see 1.5
     row  3      .*-*.*-*.   eye band, upper row
     row  4      .*-*.*-*.   eye band, lower row
     row  5      .........   cheek
     row  6      ...---...   mouth (drawn at MOUTH_K = 0.34, so dimmer than the eyes)
     row  7      .........   chin
     row  8      ---------  \
     row  9      ---------   |
     row 10      ---------   |
     row 11      ---------   |
     row 12      ---------   >  body: the existing breathing up-light from _idle_awake,
     row 13      -+-+-+-+-   |  unchanged. Bright at the base, dim under the chin.
     row 14      +++++++++   |
     row 15      **#**#**#   |
     row 16      #########  /
```

Ramp used in every picture below, showing the **face mask before the global `alpha` and
`SCLERA_K` are applied**, so that the shapes are comparable:
`.` < 0.10 · `-` 0.10–0.35 · `+` 0.35–0.60 · `*` 0.60–0.85 · `#` >= 0.85.

The eyes are a **lit sclera with a dark pupil**, not a glowing dot on a dark socket. Reasons:

- On a facade, an unlit window inside a lit block is the most legible feature there is; that is
  why the Tetris hack reads at all. A dim socket around a bright dot does not read at 300 m,
  because the socket is below the visual threshold and all you see is one lit window.
- A dark pupil is anatomically what an eye looks like, so the face reads as a face rather than as
  a creature with glowing eyes.
- The dark pupil moves at sub-window resolution for free: the socket mask is multiplied by
  `1 - PUPIL_DEPTH * gaussian(pupil_row, pupil_col)`, and the gaussian takes fractional
  coordinates. No snapping.

The socket is a super-ellipse so its edges are crisp at this resolution:

```python
socket(ec) = exp(-(((CC - ec) / EYE_HC) ** SOCKET_P + ((RR - EYE_ROW) / EYE_HR) ** SOCKET_P))
```

With `EYE_HC = 1.55`, `EYE_HR = 1.05`, `SOCKET_P = 8`, this is ~1.0 on rows 3–4 x cols 1–3 (and
5–7), ~0.0005 at column 4 and row 2. A gaussian blob would bleed into the bridge and the
forehead and the eyes would merge into one smear.

### 1.3 What the pupil positions look like

**Level, far away** (a boat on the river; pupils at rest, row 3.5, cols 2.00 / 6.00):

```
     .........
     .........
     .........
     .*-*.*-*.
     .*-*.*-*.
     .........
     ...---...
```

**Looking down at the plaza, centred** (someone at the pedestal; off_r = +0.44):

```
     .........
     .........
     .........
     .#+#.#+#.
     .*.*.*.*.
     .........
     ...---...
```

The dark cell has moved to the lower row of each socket. From the street this reads as the
building looking at its own feet.

**Looking right at a car** (off_c = +0.68 left eye, +0.55 right eye — the left eye turns further,
which is convergence):

```
     .........
     .........
     .........
     .#+-.#++.
     .#+-.#++.
     .........
     ...---...
```

**Mid-blink** (lid = 0.55). The lid edge is a sigmoid sweeping down through the socket, the same
shape and direction as the DUSK lid in `_render_dusk`:

```
     .........
     .........
     .........
     .........
     .-.-.-.-.
     .........
     ...---...
```

**Closed** (lid = 1.0). The socket is gone, but a faint lid line is drawn at row 4.05 so that a
blink — and a whole night's sleep — reads as two dashes rather than as the lights failing:

```
     .........
     .........
     .........
     .........
     .---.---.
     .........
     ...---...
```

**Asleep, dreaming** (lid = 1.0, REM on). The lid line is not flat: it is brighter where the
eyeball pushes against it from underneath, and that bright part slides as the pupils move. The
same picture two seconds apart, pupils drifting left:

```
     .........            .........
     .........            .........
     .........            .........
     .........            .........
     .-+-.-+-.            .+--.+--.
     .........            .........
     ...---...            ...---...
```

This is the whole of the night face: two dashes, breathing with the body, with a slow bulge
travelling under them. §4.4 covers when it is drawn.

**Drowsing** (lid_bias = 0.45, half-lidded, no presence for 45 s):

```
     .........
     .........
     .........
     .........
     .+-+.+-+.
     .........
     ...---...
```

**Startled** (a click on the tower; `EYE_HR` lerps to `EYE_HR_WIDE = 1.55` for 1.2 s, so the
socket grows into rows 2 and 5, and the mouth opens into a two-row blob):

```
     .........
     .........
     .---.---.
     .*-*.*-*.
     .*-*.*-*.
     .---.---.
     ...+++...
     ....-....
```

### 1.4 Coexistence with the up-light

The face draws **after** the up-light, into the same `Canvas`, using `Canvas.mask(..., "set")` for
the sclera. That mode lerps the existing pixels toward the sclera colour weighted by the mask, so:

- the lit part of the socket becomes a clean cool white and does not merely add to the warm glow
  (adding would wash the pupil out as the day's energy rises);
- where the pupil hole has cut the mask to near zero, the **existing warm up-light shows through**,
  so the pupil is a warm-dim hole in a cool-white block rather than a black square. That is both
  prettier and safer: no part of the tower reads as switched off.

The mouth and the lid line use `"max"`, which is additive-safe and cannot dim anything. The lid
line is a cached mask rather than a `cv.line` call, because it has to be multiplied by the REM
bulge of §1.3 before it is painted.

Sclera colour is cool (`(0.92, 0.95, 1.00)`) against the up-light's warm
`(1.0, 0.55, 0.15) → (1.0, 0.9, 0.7)`. The hue separation is what makes the eyes pop out of the
body glow; brightness alone is not enough at the top of the tower where the glow is already dim.

### 1.5 What the face does not have

- **No brows.** A lit 3-cell dash one row above a lit 3x2 socket merges into a single 3x4 blob at
  300 m; it costs the eyes their shape and buys an expression nobody can see. Expression comes
  from lid height and socket width instead. If Ashrit wants brows after the plaza test, they are
  four lines: a `cv.line` at row 1.9, cols 0.7–3.3 and 4.7–7.3, at `k = 0.18 * startle`, so they
  only appear when the eyes widen.
- **No nose.** There are 9 columns; column 4 is the bridge and must stay dark or the two eyes
  become one band.
- **No lower lid, no lashes.** No room.
- **A mouth, but a quiet one.** `MOUTH_K = 0.34` against the sclera's 0.55, three blobs of radius
  0.36 at columns 2.8 / 4.0 / 5.2 on a parabola whose curvature is one float in `[-0.6, +0.6]`
  (negative = corners up = smile). Curvature is honestly marginal at this resolution; the mouth's
  real job is to complete the face so the two bright blocks above it are read as eyes rather than
  as two lit offices, and it ships on. If the plaza test says it reads as a random lit window,
  `MOUTH_K = 0.0` removes it and the eyes still work — one constant, kept as an escape hatch
  rather than as a question.

---

## 2. Gaze behaviour

### 2.0 The governing principle: no crazy eyes

Every number in this section is tuned for **calm**, and where calm and realism disagree, calm
wins. A human fixates for 200–300 ms and makes something like 200 saccades a minute. On a 90 m
tower a single saccade moves a dark cell across a whole window, in public, at a scale where
nothing else on the facade moves that fast. Eyes tuned to human statistics would read as darting,
twitchy and unsettling — an anxious building, not a living one.

So the face is deliberately about twenty times slower than a person:

1. **It commits.** A landed gaze is held for at least 1.6 s and is not corrected for small errors.
2. **It ignores most of what moves.** Cars are down-weighted to a third of a person's salience and
   most of them are never even offered as a target; a walker being watched cannot be interrupted
   by traffic.
3. **It has a hard rate ceiling.** `SACCADE_BUDGET = 10` saccades per minute, enforced by a token
   bucket, so the worst case at rush hour is bounded by construction rather than by tuning. This
   is the single most important guard in the design and §7 tests it.
4. **It never flicks in place.** Micro-saccades are removed. A held gaze stays alive on slow drift
   alone.
5. **Under lowered lids it does not move at all.** Thinking, remembering, dusk and sleep all freeze
   the gaze, so the face is only ever aiming when it is fully open.

The one place where fast eye movement is allowed is REM under closed lids (§4.4), because there
the pupils are invisible and all that reaches the street is a slow brightness gradient on a dash.

### 2.1 World coordinates

One coordinate system, in grid units, extended past the edges of the facade:

| axis | meaning | range |
|---|---|---|
| `row` | vertical, same units and direction as grid rows (0 = crown, 16 = base) | `0` (sky) … `17` (ground at the wall) … `26` (out on the road) |
| `col` | lateral, same units as grid columns; negative is off the left edge | `-15` … `23` |
| `depth` | distance out from the facade, in **column units** (1 column ≈ 2.4 m) | `1` … `150` |

`row > 17` is below the bottom of the facade, which is where everything on the ground actually is.
Keeping the world in grid units means a mouse-over on the simulator, a synthetic car and a hand
written demo button all speak the same language, and there is no metres/pixels confusion anywhere.

Reference points:

| place | row | col | depth | notes |
|---|---|---|---|---|
| pedestal at the base | 20.5 | 4.0 | 6 | where an on-site prompt comes from (~14 m out) |
| plaza | 19–21 | -6 … 14 | 5–9 | pedestrians at the foot of the tower |
| sidewalk | 19–20 | -12 … 20 | 10–14 | |
| Memorial Drive, near lanes | 20–21 | -15 … 23 | 17–21 | ~45 m out, traffic left to right |
| Memorial Drive, far lanes | 20–21 | -15 … 23 | 22–26 | traffic right to left |
| river / far bank | 14–16 | -20 … 28 | 60–90 | boats, the Boston side |
| horizon | 6–10 | 0–8 | 150 | what it looks at when it looks at nothing |

### 2.2 Pupil aiming

Both eyes aim at the same world point, which is what produces different offsets per eye. For the
eye whose socket centre is at column `ec`:

```python
dx = col_w - ec                               # lateral, column units
dy = (row_w - EYE_ROW) * CELL_ASPECT          # vertical, converted to column units
dz = max(depth_w, 1.0)                        # out from the facade, column units

off_c = MAX_OFF_C * dx / hypot(dx, dz)        # sin(azimuth)
off_r = MAX_OFF_R * dy / hypot(dy, dz)        # sin(elevation)

near   = clamp(1.0 - dz / CONVERGE_NEAR)      # 1 at the wall, 0 beyond CONVERGE_NEAR
off_c += CONVERGE_GAIN * near * (1.0 if ec < 4.0 else -1.0)   # both eyes turn inward up close
```

`off_c` and `off_r` are sines of the rotation angles, which is what a real eye's pupil offset is
proportional to. The convergence term is the only piece that is not physics: it exaggerates the
cross-eyed look for things within about 34 m, because the true convergence angle for a 9 m eye
separation at that distance is small and we want it visible.

Worked values:

| target | left `off_c` | right `off_c` | pupil separation | `off_r` |
|---|---|---|---|---|
| horizon, centred (row 8, col 4, depth 150) | +0.01 | −0.01 | 3.98 | +0.03 |
| person on the plaza, left (row 20, col −2, depth 6) | −0.47 | −0.68 | 3.79 | +0.44 |
| car, far right (row 20, col 16, depth 22) | +0.46 | +0.35 | 3.89 | +0.44 |
| pedestal (row 20.5, col 4, depth 6) | +0.32 | −0.32 | 3.36 | +0.44 |
| pointer on the facade (row 3, col 1, depth 3) | −0.62 | −0.85 | 3.77 | −0.15 |

Pupil separation drops below the 4.0-column socket separation for everything nearer than the
horizon; the pedestal produces the most obvious convergence, which is correct, because that is the
one case where someone is standing right under the tower talking to it.

### 2.3 Saccades, pursuit, drift

Eyes do not glide. The aimed offsets from §2.2 are a *desired* position; the drawn position is
produced by a ballistic saccade machine, one clock for both eyes (eyes always move together):

- **Budget first.** A saccade may only start if the token bucket has a token:
  `tokens = min(BUCKET_MAX, tokens + dt / SACCADE_REFILL)`, `SACCADE_REFILL = 60 / SACCADE_BUDGET
  = 6.0 s`, `BUCKET_MAX = 3`. Launching spends one. If the bucket is empty the eyes stay where
  they are; nothing queues up and fires later. This is the ceiling of §2.0 and it is checked
  before anything else, so no amount of movement below can make the eyes busy.
- **Trigger.** If `max(|desired - current|)` across both eyes exceeds `SACCADE_TRIGGER = 0.45`
  columns — more than half a window of pupil travel — and at least `HOLD_MIN_S = 1.6 s` has passed
  since the last landing, start a saccade.
- **Flight.** Record `from` and `to` for both eyes; duration
  `SACCADE_S = clamp(0.13 + 0.10 * amplitude, 0.13, 0.28)`; interpolate with `ease_out` from
  `common.canvas`. Still **ballistic**: `to` is frozen at launch and not re-aimed mid flight, even
  if the target moves. Chasing during flight is the single thing that makes software eyes look
  like a cursor. 130–280 ms still reads as a snap rather than a glide; it is the *frequency* that
  was the problem, not the speed.
- **Hold.** Between saccades the pupil sits at the landed offset plus drift and ignores errors
  under the trigger. With a 0.45-column trigger and a 1.6 s floor, a person walking across the
  plaza is tracked in four or five deliberate steps rather than continuously corrected.
- **Smooth pursuit.** If the target has a lateral velocity (`vcol`, from the presence event) and
  the residual error is under the trigger, the held offset creeps toward the desired one at up to
  `PURSUIT_RATE = 0.55` columns of pupil travel per second. That is tuned to a pedestrian: a
  walker at 0.58 columns/s of *world* motion needs well under 0.1 columns/s of pupil motion at
  plaza depth, so pursuit keeps up with people effortlessly and cannot be dragged across the
  facade by a car. A car that outruns pursuit is simply lost, and losing it is fine.
- **Micro-drift.** Two incommensurate sines per axis with periods 17 s and 29 s, amplitudes
  `DRIFT_C = 0.075` columns and `DRIFT_R = 0.038` rows. This is the only thing keeping a held gaze
  from looking frozen, so it is slightly stronger than it was, and slow enough that it can never
  be read as a movement.
- **No micro-saccades.** `MICRO_AMP = 0.0`. They were the largest contributor to twitchiness and
  the thing they exist to prevent — a dead-still pupil — is already handled by drift.

Dead reckoning: the presence event carries `vcol`, so the Face extrapolates
`col_now = col + vcol * (t - target_t)` between updates. The traffic sensor can then push at
3 Hz and the tracking is still smooth.

The worst case is now bounded arithmetically rather than by taste: at most
`SACCADE_BUDGET * minutes + BUCKET_MAX` saccades in any window, which is 13 in the first minute
and 10 per minute thereafter, whatever the plaza is doing.

### 2.4 Blinking

Human blinks are 100–150 ms, which at 30 fps is 3–4 frames and reads as a glitch, not a blink.
The blink is deliberately slowed to **340 ms**: 0.12 s closing, 0.05 s shut, 0.17 s opening, with
`ease_in_out` on both ramps. Interval `uniform(4.0, 9.0) s`; with probability 0.12 it is a double
blink with a 0.22 s gap, which is also what the DAWN sequence does today (see §4.2). With
probability 0.35 a saccade of amplitude > 0.5 drags a blink along with it, which is a real
phenomenon (gaze-evoked blinking); now that saccades are rare it is an accent on a deliberate
movement rather than a source of flutter, so the probability goes up while the total goes down.

The lid renders as a soft vertical step, same form as the DUSK lid:

```python
edge = EYE_R0 - 0.7 + lid * (EYE_ROWS + 1.4)          # travels from above row 3 to below row 4
open_mask = 1.0 / (1.0 + exp(-(RR - edge) * LID_EDGE_SOFT))
```

`lid = max(blink_lid, lid_bias, sleep)` where `lid_bias` is the autonomous droop (drowsing) and
`sleep` is the floor imposed by the phase machine (§4.1): 0 by day, ramping to 1 through dusk, 1
all night, 0.8 while thinking or remembering. Above `LID_LINE_AT = 0.78`, a lid line is drawn at
row `EYE_ROW + 0.55` at `LID_LINE_K * lid`, so a fully closed eye is two dim dashes.

Whenever `lid >= 0.5` the gaze machine is **frozen**: no saccades, no pursuit, no scan retargeting.
There is no point aiming an eye nobody can see, and an eye that snaps while half shut is the
"crazy eyes" failure in its purest form. Blinks themselves do not freeze anything — they are too
short — but drowsing, dusk, thinking and sleep all do.

### 2.5 State machine

```
                        presence fresher than its ttl
        ┌──────────────────────────────────────────────────────┐
        │                                                      ▼
   ┌────────┐  no presence for 10 s   ┌──────┐   presence   ┌───────┐
   │ DROWSE │◄────────────────────────│ SCAN │─────────────►│ TRACK │
   └────────┘    quiet for 45 s       └──────┘              └───────┘
        │                              ▲    │  sleep >= 0.9      │
        └──────────────────────────────┼────┴────────────────────┘
                                       │         ▼
                          wake() at    │    ┌───────┐
                          _enter(DAY)  └────│ SLEEP │  lids shut, REM under them
                                            └───────┘
```

| state | entered when | pupils | lids | blinks |
|---|---|---|---|---|
| `TRACK` | a presence is fresher than its `ttl` | aim at the target per §2.2, pursuit on | `lid_bias = 0` | normal |
| `SCAN` | no fresh presence for `IDLE_AFTER = 10 s` | a new random plausible target every `uniform(5.0, 11.0) s` | `lid_bias = 0.08` | normal |
| `DROWSE` | no presence at all for `DROWSE_AFTER = 45 s` | frozen (lid >= 0.5); target drifts toward the horizon | `lid_bias` ramps to `0.45` over 10 s | duration x1.6; 20 % chance of a 0.6 s long blink |
| `SLEEP` | `sleep >= 0.9` from the phase machine (all of NIGHT, the tail of DUSK) | frozen for aiming; the REM machine of §4.4 owns them | `lid = 1`, lid line breathing with the body | suspended; REM instead |
| `HIDDEN` | `alpha < 0.05` — a performance owns the facade (§4.1) | frozen, presence age frozen too | — | suspended |

Additive, not a state: `STARTLE`, 1.2 s, triggered by a `touch` event or by a presence arriving
while in `DROWSE`. Lids snap to 0 over 0.06 s, the socket widens (`EYE_HR → EYE_HR_WIDE`), the
saccade to the new target is forced with a 0.10 s duration, the mouth opens. Startle is the one
thing allowed to bypass the token bucket, and only once every `STARTLE_MIN_GAP = 3 s`, so somebody
clicking the tower repeatedly can make it jumpy and nothing else can. Startle does nothing at all
in `SLEEP`: poking a sleeping building does not wake it.

`SCAN` target weights (this is what "looking around when nothing is there" means concretely):

| weight | what it looks at | row | col | depth |
|---|---|---|---|---|
| 0.55 | the plaza below | `uniform(19, 21)` | `uniform(-6, 14)` | `uniform(5, 9)` |
| 0.15 | the road | `uniform(20, 21)` | `uniform(-12, 20)` | `uniform(17, 26)` |
| 0.15 | the river and the far bank | `uniform(14, 16)` | `uniform(-10, 18)` | `uniform(60, 90)` |
| 0.05 | the sky | `uniform(-4, 2)` | `uniform(2, 6)` | `uniform(40, 80)` |
| 0.10 | nothing — unfocused | pupils to rest, `lid_bias = 0.30` for 1.5 s | | |

Scanning is on the same token bucket as everything else, so at one target every 5–11 s it uses at
most half the budget and leaves room for something real to appear.

### 2.6 Constant table

Geometry (all in `face.py`):

| constant | value | why |
|---|---|---|
| `CELL_ASPECT` | `2.0` | row pitch / column pitch; every vertical number derives from it |
| `FACE_R0, FACE_R1` | `1, 7` | the only rows the face may paint |
| `EYE_R0, EYE_ROWS` | `3, 2` | sclera occupies rows 3–4 |
| `EYE_ROW` | `3.5` | socket centre row |
| `EYE_CL, EYE_CR` | `2.0, 6.0` | socket centre columns; separation 4, bridge at column 4 |
| `EYE_HC` | `1.55` | socket half-width, columns |
| `EYE_HR` | `1.05` | socket half-height, rows |
| `EYE_HR_WIDE` | `1.55` | socket half-height while startled |
| `SOCKET_P` | `8` | super-ellipse exponent: flat top, crisp edge |
| `PUPIL_SC, PUPIL_SR` | `0.60, 0.80` | pupil hole sigma (columns, rows) |
| `PUPIL_DEPTH` | `0.95` | how far the hole darkens the sclera |
| `MAX_OFF_C, MAX_OFF_R` | `0.85, 0.45` | pupil travel; `0.45 * CELL_ASPECT ≈ 0.85` |
| `SCLERA` | `(0.92, 0.95, 1.00)` | cool white, separates from the warm body |
| `SCLERA_K` | `0.55 + 0.20 * energy` | brighter when the day has been busy |
| `LID_EDGE_SOFT` | `3.5` | sigmoid sharpness, matches `_render_dusk` |
| `LID_LINE_AT, LID_LINE_K` | `0.78, 0.22` | the closed-eye dash |
| `NIGHT_LID_K`, `NIGHT_BREATH_S` | `0.26`, `8.0` | the sleeping dash, and the breath period it shares with `_render_night` |
| `REM_BULGE`, `REM_SC` | `0.45`, `0.80` | how much brighter the dash gets over the pupil, and the bulge's width in columns |
| `MOUTH_R, MOUTH_SPAN` | `6.4, 1.2` | 2 rows below the eye line = 4 physical units = eye separation |
| `MOUTH_RAD, MOUTH_K` | `0.36, 0.34` | three blobs, dimmer than the eyes |
| `MOUTH_CURVE0` | `-0.2` | faintly content at rest |

Behaviour. The "was" column is the first draft's value, kept where the change is the whole point:

| constant | value | was | note |
|---|---|---|---|
| `SACCADE_BUDGET` | `10` / minute | — | hard ceiling, token bucket; the invariant of §2.0 |
| `SACCADE_REFILL`, `BUCKET_MAX` | `6.0 s`, `3` | — | `60 / SACCADE_BUDGET`; the bucket allows a short burst then throttles |
| `SACCADE_TRIGGER` | `0.45` columns | `0.18` | the eyes ignore anything under half a window of pupil travel |
| `HOLD_MIN_S` | `1.6 s` | `0.25 s` | a landed gaze is committed |
| `SACCADE_S` | `clamp(0.13 + 0.10 * amp, 0.13, 0.28)` | `0.07 … 0.16` | still a snap, just not a flick |
| `PURSUIT_RATE` | `0.55` columns/s | `1.6` | tuned to a walker; a car outruns it and is lost |
| `DRIFT_C, DRIFT_R` | `0.075, 0.038` | `0.055, 0.028` | slightly stronger, since it is now the only thing keeping a held gaze alive |
| `DRIFT_PERIODS` | `(17.0, 29.0) s` | — | slow enough that drift can never read as a movement |
| `MICRO_AMP` | `0.0` | `0.11` | micro-saccades removed |
| `FREEZE_LID` | `0.5` | — | at or above this lid the gaze machine stops entirely |
| `PRESENCE_TTL` | `4.0 s` | `2.5 s` | it does not give up on someone because one push was missed |
| `IDLE_AFTER`, `SCAN_EVERY` | `10.0 s`, `(5.0, 11.0) s` | `6.0 s`, `(1.6, 4.0) s` | it looks around slowly |
| `BLINK_EVERY` | `(4.0, 9.0) s` | `(3.2, 7.0) s` | |
| `BLINK_ON_SACCADE_P` | `0.35` | `0.25` | |
| `DOUBLE_BLINK_P`, `DOUBLE_GAP` | `0.12`, `0.22 s` | `0.18`, `0.22 s` | |
| `BLINK_S` | `0.34 s` (0.12 close / 0.05 shut / 0.17 open) | same | |
| `PEDESTAL`, `PEDESTAL_HOLD` | `(20.5, 4.0, 6.0)`, `25 s` | same | |
| `CONVERGE_GAIN`, `CONVERGE_NEAR` | `0.30`, `14` | same | |
| `DROWSE_AFTER`, `DROWSE_LID`, `DROWSE_RAMP` | `45 s`, `0.45`, `10 s` | same | |
| `WAKE_S`, `STARTLE_S`, `STARTLE_MIN_GAP` | `0.18 s`, `1.2 s`, `3.0 s` | `0.18 s`, `1.2 s`, — | |
| `FADE_IN_S`, `FADE_OUT_S` | `0.9 s`, `0.35 s` | same | |
| `REM_EVERY`, `REM_FLICK_S` | `(0.6, 2.0) s`, `0.10 s` | — | the one fast thing in the design, and it happens under closed lids |
| `DREAM_LEAD_S`, `SURFACE_LEAD_S` | `1.2 s`, `2.0 s` | — | the night hand-over windows of §4.4 |
| `DEEP_K` | `0.62` | — | the sleeping face is fainter in deep sleep, and never absent |
| `DEEP_SETTLE_S`, `DESCENT_RISE_S` | `6.0 s`, `4.0 s` | — | the ramps into and out of `DEEP_K`, so no stage boundary steps |

---

## 3. Where "traffic and passers-by" comes from

Nothing is watching. The building guesses, plausibly, from the time of day, and the guess is the
work — it seems like sensing and it is not, and that is the design rather than a stage on the way
to a camera.

| source | what it gives | role |
|---|---|---|
| **synthetic plaza** — new `sensors/traffic.py` | cars and pedestrians crossing below on plausible, hour-dependent, seeded schedules | **the source.** Always on, on the real building and in the simulator alike. |
| simulator mouse / touch — already wired; `common/web/sim.html` posts `{"type":"mouse", r, c, nr, nc, over}` on move and `{"type":"touch", down, r, c}` on click, and `app.py::on_event` ignores both today | a point on the facade itself, at 25 Hz | **override.** Highest salience. The eyes follow the cursor; a click startles it. This is the demo and the thing every web viewer will try. |
| on-site prompt channel — already in `app.py`; `ONSITE = ("pedestal", "onsite", "qr", "plaza", "speech")` and every day entry carries `channel` | somebody is physically standing at the base **right now** | **override.** A prompt from an on-site channel means a person is there; the building looks down at the pedestal for 25 s. Remote channels (`web`, `phone`, `sms`) create no presence, which is decision §5's asymmetry expressed as behaviour. |
| time of day — already have the clock | arrival rates | folded into the plaza's rate table, and into `DROWSE_AFTER` (3 a.m. gets drowsy faster) |

**Random-looking, not random.** The plaza is seeded: to anyone watching it is arbitrary traffic, and
to a test or a recorded demo it is the same traffic every time. Those are not in tension, they are
the same requirement seen from two sides, and §3.2 gets it with a fixed-step model and one
`random.Random(seed)`.

**The bar is plausible and calm, not accurate.** This is not a traffic simulation and nothing
depends on its fidelity. There are no lanes to conflict over, no signals, no following distances,
no attempt to match real counts on Memorial Drive. The rate table in §3.2 is coarse on purpose —
nine hour bands and two numbers each — and the only properties that matter are that things cross
slowly, that there are more of them at 17:00 than at 03:00, and that the eyes have something
believable and unhurried to rest on.

The seam is kept, without a migration plan: because everything arrives as one `presence` event
(§3.1), a real sensor — a camera, a mic, the pedestal of HANDOFF §8.3 — would be a new file that
pushes the same event, and `face.py` would not change. That is future-proofing, not a roadmap.

Not used: phone gyros via the `/say` page (needs the page open and https, and says nothing about
where anyone is); Wi-Fi or BLE counting (needs hardware, and raises the privacy question of a
camera with none of the payoff).

### 3.1 The event

One new event type, following the existing vocabulary (lower-case `type`, flat fields, a `source`):

```json
{"type": "presence", "source": "traffic", "kind": "person",
 "row": 20.1, "col": -3.2, "depth": 7.0,
 "vcol": 0.58, "salience": 0.70, "ttl": 4.0, "id": 1174}
```

| field | type | meaning |
|---|---|---|
| `type` | `"presence"` | |
| `source` | str | `traffic` / `web` / `pedestal` / `timeline` — set by the producer, defaulted to `web` by `/input` |
| `kind` | str | `car` / `bike` / `person` / `group` / `pointer` / `pedestal`; only used for salience and status text |
| `row`, `col`, `depth` | float | world coordinates, §2.1 |
| `vcol` | float | lateral velocity, columns/s, for dead reckoning and pursuit; default 0 |
| `salience` | float 0–1 | how much it deserves a look |
| `ttl` | float | seconds this sighting is trusted; default `PRESENCE_TTL` |
| `id` | int, optional | agent identity, so pursuit knows it is the same car |
| `gone` | bool, optional | this sighting has ended (the agent left, the mouse left the canvas) |

Handled in `on_event` as one new branch beside the existing `weather` / `text` / `spec` branches:

```python
elif t == "presence":
    self.face.presence(ev, ctx.t)
elif t in ("mouse", "touch"):
    self.face.pointer(ev, ctx.t)          # translates r/c/over/down into a presence
```

`Face.pointer` maps the simulator's cell coordinates straight into the world: `row = ev["r"]`,
`col = ev["c"]`, `depth = 3.0`, `kind = "pointer"`, `salience = 0.95`, `ttl = 1.2`, and
`gone = not ev.get("over", True)`. A `touch` with `down: true` additionally calls
`Face.startle(t)`. Because the pointer is at depth 3, hovering near the eyes makes the tower go
briefly cross-eyed, which is correct and funny.

Salience by kind, before modifiers — cars are deliberately far below people (was `car 0.45`):

| kind | salience |
|---|---|
| `car` | `0.22` |
| `bike` | `0.45` |
| `person` | `0.70` |
| `group` | `0.90` |
| `pointer` | `0.95` |
| `pedestal` | `1.00` |

Modifiers: `* (1 + 0.5 * clamp(1 - depth / 30))` for proximity, and a novelty bonus of
`NOVELTY_K = 0.30` for the first `NOVELTY_S = 1.5 s` after an id appears, scaled to `0.3 *
NOVELTY_K` for `car` and `bike` so a stream of new cars cannot keep winning the novelty term.

The arithmetic that makes "prefer people" a fact rather than an intention: a fresh car at road
depth scores `0.22 * 1.18 + 0.09 = 0.35`; a person on the plaza scores `0.70 * 1.40 = 0.98`, or
`1.28` while new. With `SWITCH_MARGIN = 0.35` a car would need to reach 1.33 to interrupt a
watched person, which it cannot. Cars are therefore only ever watched when the plaza is empty,
which is the difference between "it watched a car go by" and "it is a metronome".

### 3.2 `sensors/traffic.py`

Structured exactly like `sensors/weather.py`: a module of plain functions and constants plus one
`threading.Thread` subclass that pushes onto the bus and never touches the canvas.

```python
LANES: dict[str, dict]          # the table in §2.1, as data
RATES: dict[range, tuple]       # arrivals per minute by hour: (pedestrians, cars)
CLASS_CHANGE = (25, 30, 55, 60) # minutes past the hour; x3 pedestrians between 09:00 and 16:00
CAR_LOOK_P = 0.15               # fraction of cars the eyes are even allowed to consider

@dataclass
class Agent:
    ident: int; kind: str; row: float; col: float; depth: float; vcol: float; born: float
    lookable: bool = True       # False for 85 % of cars: in the model, invisible to the eyes

class Plaza:
    """Deterministic crowd. Pure model, no threads, no clock of its own."""
    def __init__(self, seed: int = 0, rate_scale: float = 1.0) -> None
    def step(self, dt: float, hour: float) -> None      # spawn, advance, retire
    def salient(self, t: float) -> Agent | None         # lookable only, with hysteresis
    def __len__(self) -> int

class TrafficSensor(threading.Thread):
    def __init__(self, bus: InputBus = BUS, seed: int = 0, rate_scale: float = 1.0) -> None
    hour: float = 12.0          # plain float, written by the main loop, read here
    rate_scale: float           # plain float, written by the control panel handler
    def run(self) -> None       # while True: self._tick(); time.sleep(TICK)
    def _tick(self) -> None     # one fixed-dt step + at most one bus push
```

Determinism comes from three choices:

1. `Plaza` advances by a **fixed** `dt = TICK = 1/8 s` per tick, never by wall-clock elapsed time.
   Scheduling jitter cannot change the sequence.
2. All randomness is one `random.Random(seed)` owned by the `Plaza`.
3. The thread is a thin shell around `Plaza` and `_tick()`, so tests drive `Plaza` and `_tick`
   directly and never start a thread or sleep.

Rate table (arrivals per minute, before `rate_scale` and the class-change multiplier). Coarse on
purpose — see §3's note on the bar. Nothing downstream is sensitive to these numbers; they only
have to make 17:00 busier than 03:00:

| hours | pedestrians | cars |
|---|---|---|
| 00–05 | 0.2 | 6 |
| 06–07 | 1.0 | 20 |
| 08–09 | 4.0 | 38 |
| 10–11 | 3.0 | 26 |
| 12–13 | 5.0 | 30 |
| 14–16 | 3.0 | 26 |
| 17–18 | 4.0 | 40 |
| 19–21 | 2.0 | 22 |
| 22–23 | 0.8 | 12 |

Speeds, from the real thing: a car at 40 km/h is 11 m/s, which at 2.4 m per column is
**4.6 columns/s**, so it crosses `COL_IN = -15` to `COL_OUT = 23` in about 8 s. A pedestrian at
1.4 m/s is **0.58 columns/s** and takes about 65 s. `MAX_AGENTS = 40` caps the list; at the 17:00
rate about 5 cars are in view at once.

That speed difference is exactly why the eyes prefer people. A pedestrian is 65 seconds of slow,
near, human motion that pursuit handles without a single saccade past the first. A car is 8
seconds that would drag the pupils across the whole facade and then abandon them mid-travel — the
worst available behaviour, and the reason cars are down-weighted in §3.1 and additionally filtered
here: only `CAR_LOOK_P = 0.15` of cars are marked `lookable` at spawn (decided from the seeded
rng, so it is reproducible), and `salient()` never returns the rest. The crowd stays busy; the
eyes do not. Watching one car in a while is calm. Watching every car is a metronome.

Salient selection with hysteresis, so the eyes do not shop around: keep the current agent unless
another beats it by `SWITCH_MARGIN = 0.35` (was 0.15), or the current one has left, or it has been
watched for more than `WATCH_MAX = 20 s` (was 6 s), at which point a different id is preferred if
one exists. Twenty seconds is long enough to watch someone all the way across the plaza.

Push policy: a `presence` event when the salient agent changes, and otherwise every
`PUSH_EVERY = 0.33 s` to refresh the position of the one being watched; `{"gone": true}` when it
leaves. That is about 3 events/s on a bus the loop drains 30 times a second. Agents are retired at
`COL_OUT` or after `MAX_LIFE = 180 s`, whichever comes first, so nothing can accumulate.

If the sensor is disabled with `--no-traffic` or fails to start, nothing breaks: the face has no
presence to track, so it sits in `SCAN` and looks slowly around the plaza — which is roughly
today's wandering behaviour, with eyes.

The clock: the app writes `self.traffic.hour = self.hour` in the same `ctx.frame_index % 6 == 0`
branch that already updates the status panel. A single float assignment from the main thread, no
lock, no blocking — and it means `--time-scale 600` makes the traffic rush-hour too.

---

## 4. Integration with the phase machine

### 4.0 The whole day as one arc for the eyes

The eyes are never switched off and never jump. They are the same pair of eyes from one dawn to
the next, and every phase is a position on one continuous curve. This is the single place that
describes it; the subsections below are only the mechanics.

| when | lids | pupils | what the street sees |
|---|---|---|---|
| DAWN, first 60 % | shut (`sleep = 1`) | still | light climbing the tower; no face yet |
| DAWN, last 40 % | shut | still | the stretch and the two whole-body blinks — the existing abstract gesture (§4.2) |
| `_enter(DAY)` | open over 0.9 s, then one blink | settle from rest | the eyes open for the first time that day |
| DAY, idle | open, blinking every 4–9 s | watching the plaza; scanning when it is empty | the face, awake |
| DAY, thinking or remembering | `sleep = 0.8`, near shut | frozen | eyes lowered while the shimmer climbs or a daydream plays |
| DAY, performing | not drawn | frozen, presence age frozen | the scene owns the facade; the eyes dissolve out with the transition |
| DUSK, `prog` 0 → 0.3 | droop to shut, meeting the body lid at the same rows | frozen from `lid >= 0.5` | the eyelids close, and the tower's own lid arrives behind them |
| DUSK, `prog` 0.3 → 1 | shut, then masked out entirely by the body lid | still | the yawn, eyes already closed |
| NIGHT, `descent` | shut, breathing | REM: slow bulge sliding under the lid line | two dim dashes, dreaming |
| NIGHT, `dream` | shut, handed over in 1.2 s | REM, then nothing | the dream owns the facade |
| NIGHT, `surfacing` | shut, returning over 2.0 s | still | the dashes come back as the dream clears |
| NIGHT, `deep` | shut, breathing, fainter (`DEEP_K`) | still — no REM in deep sleep | two very dim dashes, breathing; still a face |
| DAWN again | shut | still | and round |

The two hard edges in that list are both at NIGHT `dream`, and §4.4 gives them explicit
hand-over windows so nothing pops.

### 4.1 The gate: drawn, and how shut

This is not a boolean any more. One method returns both halves of the question — whether the face
is in this frame at all, and how closed its lids are:

```python
def _face_gate(self, phase: str, prog: float) -> tuple[bool, float, float]:
    """(drawn, sleep, rem): is the face in this frame, what is the floor on its eyelid,
    and is it dreaming behind it.

    sleep is a lid floor: 0 = free to open, 1 = shut. drawn is False only when something
    else owns the facade, which is a performance and nothing else.
    """
    if not self.face_enabled:                       # --no-face, or the control-panel toggle
        return False, 0.0, 0.0
    if phase == "NIGHT":                            # asleep, eyes closed (4.4)
        return True, 1.0, (1.0 if self.dream_stage in ("descent", "dream") else 0.0)
    if phase == "DAWN":
        return False, 1.0, 0.0                      # DAWN has its own choreography (4.2)
    if phase == "DUSK":
        return True, clamp(prog / 0.3), 0.0         # the lids come down (4.3)
    if self.current is not None or self.queue:      # DAY, a performance owns the facade
        return False, 0.0, 0.0
    if self.pending or self.daydream is not None:   # DAY, thinking or remembering
        return True, 0.8, 0.0
    return True, 0.0, 0.0                           # DAY, awake and watching
```

Driven from `update()`, not from `_idle_awake()`, so the machine ticks every frame in every phase
and the face never teleports when it comes back. Call site: in `update()`, after the
`self.energy = max(0.0, self.energy - dt / 40.0)` line and **before** the `if phase == "DAY":`
branch, because the phase renderers are what draw it:

```python
drawn, sleep, rem = self._face_gate(phase, prog)
self.face.energy = self.energy
self.face.update(dt, t, visible=drawn, sleep=sleep, rem=rem)
```

`Face.update` eases `self.alpha` toward `1.0` over `FADE_IN_S` or toward `0.0` over
`FADE_OUT_S`, and `Face.draw` returns immediately when `alpha < 0.01`. Consequences worth being
explicit about:

- **A performance is the only thing that removes the face.** Everything else lowers the lids
  instead, which is both calmer (§2.0: a face flickering in and out is a worse twitch than any
  pupil) and more legible — half-shut eyes say "busy", an absent face says nothing.
- **Performance start and end need no fade of their own.** `_start()` snapshots
  `self._idle_awake(t, dt)` into `prev_canvas` and `_render_day` cross-fades it with `mix()` over
  0.9 s; the face is inside that snapshot, so it dissolves out with everything else. The same
  happens in reverse when `self.current.done` sets up a `dissolve` back to idle. The
  `FADE_OUT_S` envelope only matters for the toggle and for `--no-face`.
- **Thinking (`self.pending`) lowers the lids to 0.8 and freezes the gaze.** The thinking shimmer
  is a bright band sweeping up the tower; a lowered, still face underneath it reads as
  concentration. This is the call on the question left open in the first draft: hiding the face
  every time somebody types would make it blink in and out all afternoon.
- **The daydream needs nothing beyond the same 0.8.** `_render_day` already blends `out.px` with
  the daydream canvas by `k` up to 0.4, and the face is in `out`, so it dims with everything else
  while its lids are down. Eyes lowered, remembering.

While `alpha < 0.05`, `Face.update` freezes the age of the current presence (`self.target_t +=
dt`) so that an on-site prompt's 25 s pedestal look survives the performance it triggered. The
building performs your prompt, and when the picture clears it is looking down at you. This is one
line and it is the best moment in the whole feature.

### 4.2 DAWN

`_render_dawn` today is: light climbs from the base for 60 % of the window, then a stretch, then
**two whole-body blinks** (`cv.px *= blink`, two gaussians at `a = 0.55` and `a = 0.8`), and then
`_enter("DAY")` starts the GOOD MORNING marquee.

Those two blinks are already a face gesture, done abstractly on the whole tower.
**Decision: they stay on the whole body, and `_render_dawn` is not touched at all.** The face is
not drawn during DAWN. Instead `_enter("DAY")` calls `self.face.wake(t)`, which sets `lid = 1.0`,
`alpha = 0`, and opens the lids over `WAKE_S * 5 = 0.9 s` with a blink at the end.

The morning therefore reads: light climbs the tower, the tower stretches, it blinks twice with its
whole body, and then the eyes open for the first time. That is the intended sequence — one gesture
resolving into a more specific version of itself — and it is better than the alternative of moving
the blinks onto the eyelids, which would have replaced a signature gesture of the piece with a
smaller one and would have meant editing `_render_dawn`. Nothing in DAWN changes.

### 4.3 DUSK

`_render_dusk` starts from `cv = self._idle_awake(t, dt)`, so the face appears in DUSK for free,
and the existing lid mask — which darkens every row above `lid_row = clamp(prog * 1.15) * 19 - 1`
— sweeps down over it. At `prog = 0.25` that edge is already at row 4.5, so the body's eyelid has
passed the eyes by the first quarter of dusk. That is the right gesture; it just needs the face's
own lids to lead it rather than be erased by it.

So: `_face_gate` returns `sleep = clamp(prog / 0.3)` during DUSK (§4.1), and `Face` uses it as a
floor on the eyelid. The eyelids visibly droop and close over the first 30 % of dusk, finishing
just as the body's lid arrives at the same rows — the face's own lids and the tower's meet. Past
`prog ≈ 0.3` the face is still drawn and still returns `True` from the gate, but the body lid
multiplies those rows to nothing, so it costs a few numpy operations and shows nothing. That is
the correct outcome and it needs no special case.

The gaze freezes at `lid >= FREEZE_LID = 0.5`, which happens at `prog ≈ 0.15`, so the last thing
the eyes do before dusk is hold still. The existing yawn (`prog` 0.25–0.55) then happens with the
eyes already shut, which is what a yawn looks like.

`_idle_awake` needs no knowledge of any of this — it just calls `self.face.draw(cv)` at the end —
so the only DUSK edit is the one `sleep` argument already in `update()`.

### 4.4 NIGHT: the sleeping face

At night the face is **present with its eyes closed**. `_face_gate` returns `(True, 1.0)` for the
whole of NIGHT, so `lid = 1`, the sockets are gone, and what is drawn is the lid line of §1.3: two
dim dashes at row 4.05. Their brightness is `NIGHT_LID_K * (0.55 + 0.45 * b)` where

```python
b = 0.5 + 0.5 * math.sin(t * 2 * math.pi / NIGHT_BREATH_S)     # NIGHT_BREATH_S = 8.0
```

which is character-for-character the expression `_render_night` already uses for its indigo base.
Same `t`, same formula, same phase, so the closed eyes dim and swell **with** the body instead of
sitting at a fixed level on top of a breathing tower. The 8.0 is duplicated deliberately rather
than plumbed through; §8.5 notes the coupling.

For scale: at row 4 the night base is about 0.04 in red and green and 0.14 in blue, also
breathing. The dashes at 0.14–0.26 warm-white, drawn `"max"`, sit just above it. Dim, unmistakably
there, and nowhere near bright enough to compete with a dream.

**Where it may draw, and where it must not.** `_render_night` builds its base with
`cv.vgradient(...)` and then, in the `dream` stage, does `cv.px = np.maximum(cv.px, d.px)`. The
face therefore draws at exactly one place: immediately after the `vgradient` call, before the
stage machine. Its stage-dependent strength comes from one new helper:

```python
def _sleep_alpha(self, e: float) -> float:
    """How much of the sleeping face this night stage wants. e is time since the stage began."""
    st = self.dream_stage
    if st == "dream":
        return clamp(1.0 - e / DREAM_LEAD_S)             # hand over to the dream in 1.2 s
    if st == "surfacing":
        return clamp(e / SURFACE_LEAD_S)                 # come back over 2.0 s as the dream clears
    if st == "deep":                                      # sink to a fainter, deeper sleep
        return lerp(1.0, DEEP_K, clamp(e / DEEP_SETTLE_S))
    return lerp(DEEP_K, 1.0, clamp(e / DESCENT_RISE_S))   # descent: brighten as REM begins
```

and one new line in `_render_night`, right below the `cv.vgradient(...)` line:

```python
self.face.draw(cv, self._sleep_alpha(t - self.stage_t0))
```

Stage by stage:

| stage | face | why |
|---|---|---|
| stage | `_sleep_alpha` | face | why |
|---|---|---|---|
| `descent` | `DEEP_K → 1.0` over 4 s | **yes**, with REM | the dream is being composed; the building is asleep and nothing else owns the facade. The face brightens as REM begins. The existing REM-onset colour flickers keep working — they are additive blobs at random positions and the dashes sit happily under them. |
| `dream` | `1.0 → 0.0` over 1.2 s | **the lead only**, and always *before* the `np.maximum` | a dream scene owns the whole facade. This is the one rule that must not be broken. |
| `surfacing` | `0.0 → 1.0` over 2.0 s | **yes**, fading in | the dream has ended, the tower is dim indigo again, and the eyes are still shut |
| `deep` | `1.0 → DEEP_K` over 6 s | **yes**, fainter, no REM | deep sleep: the dashes sink to `DEEP_K = 0.62` and breathe there for the rest of the 25 s |

The 1.2 s lead into `dream` is what stops the dashes popping off. Because the face is painted
*under* the `np.maximum` and `DreamPlayer` spends its own first 1.6 s fading up from black, the
closed eyes are simply swallowed as the dream brightens — a hand-over, not a cut. After 1.2 s
`_sleep_alpha` returns 0, `draw` short-circuits on `alpha < 0.01`, and for the rest of the dream
the face contributes literally nothing. Painting it *over* the maximum at any strength would leave
two dashes floating on top of a dream scene, which is the "fighting" to avoid, and would also
contradict HANDOFF §7.4: night is the show.

**Deep sleep stays visible.** `DEEP_K = 0.62`, not zero: the building keeps a face up there all
night. In numbers, the dash peaks at `NIGHT_LID_K * 0.62 = 0.161` at the top of a breath and
`0.089` at the bottom, against a night base that is 0.081–0.135 in blue and about 0.037 in red and
green at those rows. So at the top of each breath the closed eyes are clearly brighter than the
body in every channel, and at the bottom they very nearly sink into it and then come back. That is
the reading worth having — asleep, faint, unmistakably still a face — and it is better than
fading the lid line out entirely, which would leave a featureless indigo slab for 25 s out of
every cycle.

Every boundary is continuous by construction, because each stage's ramp ends where the next one
begins: `surfacing` reaches 1.0 well before its 10 s are up, so `deep` starts at 1.0 and sinks;
`deep` reaches `DEEP_K` well before its 25 s are up, so `descent` starts at `DEEP_K` and rises;
`descent` is at least 6 s, so it reaches 1.0 before the dream can start; and `dream` ends at 0.0,
where `surfacing` begins. The loop closes with no steps anywhere in it. Entering NIGHT from DUSK
is continuous too: DUSK left the lids shut and the body lid dark, so `descent` opening at
`DEEP_K` and rising reads as the face emerging with the indigo base. `_enter("NIGHT")` calls
`Face.sleep_now(t)`, which pins `lid = 1.0` and puts the state machine in `SLEEP` so nothing can
reopen the eyes before dawn.

**REM.** During `descent` (and the 1.2 s lead, where it is academic) the pupils move behind the
closed lids, and the only thing that reaches the street is the bulge of §1.3: the lid line is
multiplied by `1 + REM_BULGE * gauss(pupil_col, REM_SC)`, so the dash reads `-+-` and the bright
part slides. `REM_EVERY = uniform(0.6, 2.0) s`, flicks of `REM_FLICK_S = 0.10 s`. This is the one
fast eye movement in the whole design and it is allowed precisely because the pupils are invisible:
the visible result is a three-cell brightness gradient shifting by one cell, which cannot read as
crazy eyes. It is also the most literal available statement that the building is dreaming, and it
costs one multiply on a cached mask.

REM is **not** coupled to the dream's content, and should not be. There is no "where the dream is
looking" — a dream scene is a spec, not a position — so any mapping (the brightest column of the
dream canvas, say) would be invented, would need `Face` to read back a canvas it has no business
reading, and would resolve to three cells of dash. Real REM eye movements do not scan a scene
either. So the pupils drift autonomously, and there is no REM at all in `surfacing` or `deep`,
which is both physiologically right and visually the calmest possible ending to a cycle.

Sleep-talk is unchanged: the mumble blob is at row 9 and never touches the eye rows. A `presence`
event arriving at night is still recorded by `Face.presence`, but `SLEEP` ignores it for aiming, so
nobody can make the sleeping building look at them. If a `phase → day` override arrives, `wake()`
opens onto whatever was last seen rather than mid-scan.

---

## 5. Code structure

### 5.1 New file: `face.py` (~280 lines)

Module docstring in the house style, then the constants of §2.6, then one class. Mirrors how
`DreamPlayer` and `Performance` are built: constructed once, fed time and inputs, asked for
pixels, and completely ignorant of `App`, `Context` and the bus.

```python
class Face:
    """Two eyes, eyelids and a quiet mouth in rows 1-7, aimed at a point on the plaza below.

    The building's own idle behaviour: not a scene, not spec-driven, never something a prompt
    can ask for. update() runs the gaze/blink machine; draw() paints it over whatever the
    idle renderer has already put on the canvas.
    """

    def __init__(self, seed: int = 0, cell_aspect: float = CELL_ASPECT) -> None:
        self.rng = random.Random(seed)
        self.aspect = cell_aspect
        self.alpha = 0.0                  # 0 hidden .. 1 fully drawn
        self.energy = 0.0                 # set by the app; brightens the sclera
        self.state = "sleep"              # scan | track | drowse | sleep
        # target
        self.target = (8.0, 4.0, 150.0)   # world (row, col, depth): the horizon
        self.target_t = -1e9
        self.target_ttl = PRESENCE_TTL
        self.target_vcol = 0.0
        self.target_kind = "none"
        self.target_id: int | None = None
        self.target_sal = 0.0
        self.last_presence_t = -1e9
        self.scan_t = 0.0
        # pupils: current drawn offsets per eye, [ [off_r, off_c], [off_r, off_c] ]
        self.off = [[0.0, 0.0], [0.0, 0.0]]
        self.sac_t0, self.sac_dur = -1e9, 0.0
        self.sac_from = [[0.0, 0.0], [0.0, 0.0]]
        self.sac_to = [[0.0, 0.0], [0.0, 0.0]]
        self.hold_t = 0.0
        self.tokens = float(BUCKET_MAX)   # saccade budget, refilled in update()
        self.saccades = 0                 # lifetime count, for the status panel and the tests
        # lids and expression
        self.lid = 1.0                    # 0 open .. 1 closed; starts closed
        self.lid_bias = 0.0
        self.sleep = 1.0                  # lid floor from the phase machine (4.1)
        self.blink_t0 = -1e9
        self.blink_dur = BLINK_S
        self.next_blink = 3.0
        self.pending_double = False
        self.startle_t0 = -1e9
        self.mouth_curve = MOUTH_CURVE0
        self.mouth_open = 0.0
        # night
        self.rem = 0.0                    # 0 none .. 1 full REM; set by sleep()/the stage
        self.rem_t = 0.0
        self.rem_goal = 0.0
        # cached masks (static, computed once)
        self._socket = [_socket_mask(EYE_CL, EYE_HR), _socket_mask(EYE_CR, EYE_HR)]
        self._socket_wide = [_socket_mask(EYE_CL, EYE_HR_WIDE), _socket_mask(EYE_CR, EYE_HR_WIDE)]
        self._lid_line = [_lid_line_mask(EYE_CL), _lid_line_mask(EYE_CR)]

    # -- inputs (called from App.on_event; no I/O, no blocking) ------------
    def presence(self, ev: dict, t: float) -> None
    def pointer(self, ev: dict, t: float) -> None
    def look_at(self, row: float, col: float, depth: float = 8.0, *, salience: float = 1.0,
                ttl: float = PRESENCE_TTL, kind: str = "person", vcol: float = 0.0,
                ident: int | None = None, t: float = 0.0) -> None
    def presence_gone(self, ident: int | None = None, t: float = 0.0) -> None
    def startle(self, t: float) -> None       # no-op in the sleep state
    def blink(self, t: float, dur: float = BLINK_S) -> None
    def wake(self, t: float) -> None          # lids closed, then open: called from _enter("DAY")
    def sleep_now(self, t: float, rem: float = 1.0) -> None   # lids shut for the night: _enter("NIGHT")
    def reset(self) -> None                   # forget presence: called from _enter("DAWN")

    # -- per frame ---------------------------------------------------------
    def update(self, dt: float, t: float, visible: bool = True, sleep: float = 0.0,
               rem: float = 0.0) -> None
    def draw(self, cv: Canvas, alpha: float | None = None) -> None

    # -- queries (tests and the status panel) ------------------------------
    def pupil(self, eye: int) -> tuple[float, float]   # absolute grid (row, col) of a pupil
    def aim(self, eye: int) -> tuple[float, float]     # the desired offsets, pre-saccade
    def status_line(self) -> str                       # "track person r20.1 c-3.2 d7 lid 0.02 sac 14"
```

`update(dt, t, visible, sleep, rem)` in order: alpha envelope; freeze presence age and return
early if hidden; refill the saccade bucket; expire the target and pick the state; if
`lid >= FREEZE_LID` stop here, having resolved the lid; otherwise compute `aim()` for both eyes and
run the budget / saccade / pursuit / drift machine; run the blink scheduler (or, in `sleep`, the
REM machine); resolve `lid = max(blink_lid, lid_bias, sleep)`; decay startle and mouth. Pure
scalar and small-array maths, no allocation beyond two 17x9 gaussians, no I/O — safe inside the
frame loop.

`draw(cv, alpha=None)` is pure with respect to `Face` state, so calling it twice in one frame —
which `_start()` can do, since it snapshots `_idle_awake` — is harmless. Per eye:

```python
a = (self.alpha if alpha is None else self.alpha * alpha)
if a < 0.01:
    return
m = lerp(self._socket[i], self._socket_wide[i], startle)
m = m * (1.0 - PUPIL_DEPTH * _pupil_mask(pr, pc))      # the moving hole
m = m * _lid_mask(self.lid)
cv.mask(m * a, SCLERA, self.sclera_k, "set")           # lerp toward cool white; hole lets the glow through
if self.lid > LID_LINE_AT:                             # the closed lid, with the REM bulge under it
    line = self._lid_line[i] * (1.0 + REM_BULGE * self.rem * _bulge(pc))
    cv.mask(line * a * self.lid, SCLERA, self.lid_line_k, "max")
```

where `self.lid_line_k` is `LID_LINE_K` by day and `NIGHT_LID_K * (0.55 + 0.45 * b)` in the sleep
state, `b` being the 8-second breath of §4.4. Then the mouth as three `cv.blob` calls on the
parabola. Cost: about seven 17x9 numpy operations per frame, which is nothing next to
`Particles.update`.

Helpers, module-level, using the existing `RR` / `CC` grids from `common.canvas`:
`_socket_mask(ec, hr)`, `_pupil_mask(pr, pc)`, `_lid_mask(lid)`, `_lid_line_mask(ec)`,
`_bulge(pc)`.

### 5.2 New file: `sensors/traffic.py` (~160 lines)

As specified in §3.2. Imports only `random`, `threading`, `time`, `dataclasses` and
`common.inputs`. It does not import `face`, `app`, `Canvas` or numpy.

### 5.3 New file: `tests/test_face.py` (~260 lines)

§7.

### 5.4 Edits to `app.py` (about 50 lines net, all additive except the blob removal)

Described by surrounding code, not line number, because another agent is editing this file.

| where | change |
|---|---|
| imports, beside `from scene import Performance, validate` | `from face import Face, PEDESTAL, PEDESTAL_HOLD` and `from sensors.traffic import TrafficSensor` |
| `add_args`, after `--journal` | `--no-face` and `--no-traffic` store-true flags |
| `setup`, next to `self.sensor = WeatherSensor(...)` | `self.face_enabled = not getattr(ctx.args, "no_face", False)`; `self.face = Face(seed=self.rng.randrange(1 << 30))`; `self.traffic = None if (self.offline_traffic) else TrafficSensor(ctx.bus, seed=self.rng.randrange(1 << 30))` then `.start()`. **Delete** `self.gaze`, `self.gaze_goal`, `self.wander_t`. |
| `setup`, inside the existing `ctx.set_controls([...])` list | the controls in §6 |
| `on_event`, after the `weather` branch | `elif t == "presence": self.face.presence(ev, ctx.t)` and `elif t in ("mouse", "touch"): self.face.pointer(ev, ctx.t)` |
| `on_event`, new branches beside `time_scale` | `face` (toggle / one-shot blink), `face_presence` (source select), `traffic_rate` (slider) |
| `on_event`, in the `spec` branch after `self._journal_append(entry)` | `if channel in ONSITE: self.face.look_at(*PEDESTAL, salience=1.0, ttl=PEDESTAL_HOLD, kind="pedestal", t=ctx.t)` |
| `update`, after the `self.energy = max(...)` line, before the phase branch | the three-line `_face_gate` + `Face.update` call from §4.1 |
| `update`, inside the existing `if ctx.frame_index % 6 == 0:` block | `self.traffic.hour = self.hour` (guarded) and the status fields in §6 |
| `_enter`, in the `DAWN` branch, beside `self.dream = None` | `self.face.reset()` |
| `_enter`, in the `DAY` branch, beside the GOOD MORNING marquee | `self.face.wake(t)` |
| `_enter`, in the `NIGHT` branch, beside `self.dream_stage, self.stage_t0 = "descent", t` | `self.face.sleep_now(t)` |
| `_idle_awake`, replacing the `self.wander_t` / `self.gaze` block and the final `cv.blob(...)` | `self.face.draw(cv)` as the last statement before `return cv` |
| `_render_night`, immediately after the `cv.vgradient((0.03, 0.03, 0.12), ...)` line and before `if stage == "descent":` | `self.face.draw(cv, self._sleep_alpha(e))` — the one night call site, above the stage machine so it can never land on top of `np.maximum(cv.px, d.px)` (§4.4) |
| new methods, beside `_idle_awake` | `_face_gate()` from §4.1 and `_sleep_alpha()` from §4.4 |
| `demo_script` | `(30.0, {"type": "presence", "kind": "person", "row": 20, "col": -4, "depth": 6, "vcol": 0.6, "salience": 0.8})` and a `touch` at 62 s, so the recorded demo shows tracking and a startle. The existing `(84.0, phase night)` already gives the sleeping face and one full dream cycle. |

No other module changes. Explicitly **not** touched: `utilities/`, `tetris.py`, `scene.py`,
`dream.py`, `genie.py`, `library.py`, `render.py`, `worlds.py`, `common/*`. `common/web/sim.html`
already sends everything needed.

Follow-up docs (slice 8): `README.md`'s "a wandering gaze" line, and two rows in `HANDOFF.md` —
one in the §1 status table, one in the §4 event vocabulary table for `presence`, plus a note that
`mouse`/`touch` are no longer ignored.

### 5.5 Should the face be spec-driven? No.

Recommendation: the face is **not** a `scene.SCHEMA` field, and `validate()` does not change.

- CLAUDE.md: the model never draws pixels. A face is a drawing. The model has no business
  emitting one.
- The face is the building's idle behaviour between performances, in the same category as the
  breathing up-light, the DAWN stretch and the DUSK yawn — none of which are spec fields either.
- `FEATURES.md` already records the rule that faces are never sprites. A `face` spec field would
  be the same mistake through a different door, and would let a prompt put a face on the tower in
  the middle of a rocket launch.
- It would collide with the sprite for the same 9 columns, which is the exact conflict the
  word-plays-at-the-end rule exists to avoid.

The one adjacent thing that is tempting and should still be refused: a spec field saying "look at
the person who asked for this at the end of the scene". If that behaviour is wanted, it belongs in
the phase machine as a post-performance gesture (which §4.1's frozen presence age already gives
for free), not in the spec.

---

## 6. Controls and observability

Appended to the existing `ctx.set_controls([...])` list in `setup`, after the clock sliders and
before the prompt buttons:

```python
{"type": "note", "text": "Move the mouse over the tower and the eyes follow it. Click to poke it."},
{"type": "toggle", "label": "Face", "value": True, "event": {"type": "face"}, "key": "on"},
{"type": "select", "label": "Presence", "options": ["traffic", "pointer", "both", "off"],
 "value": "both", "event": {"type": "face_presence"}, "key": "mode"},
{"type": "slider", "label": "Traffic rate (x)", "min": 0, "max": 5, "step": 0.25, "value": 1,
 "event": {"type": "traffic_rate"}, "key": "x"},
{"type": "button", "label": "look down", "event": {"type": "presence", "kind": "person", "row": 20.5, "col": 4, "depth": 6, "salience": 1.0}},
{"type": "button", "label": "look left", "event": {"type": "presence", "kind": "person", "row": 20, "col": -6, "depth": 7, "salience": 1.0}},
{"type": "button", "label": "look right", "event": {"type": "presence", "kind": "car", "row": 20.5, "col": 18, "depth": 20, "vcol": -4.6, "salience": 1.0}},
{"type": "button", "label": "blink", "event": {"type": "face", "blink": True}},
```

Note that `presence` is not a `text` event, so when `GREENDREAM_INPUT_TOKEN` is set these buttons
need `/?key=TOKEN` exactly like the phase and clock controls. That is correct: they change what the
building does.

Status, added to the existing `ctx.set_status(...)` call in the `frame_index % 6` block:

```python
face=self.face.status_line(),          # "track person r20.1 c-3.2 d7 sal 0.98 lid 0.02 sac 14"
traffic=(len(self.traffic.plaza) if self.traffic else 0),
```

`status_line()` covers state, target kind, world position, salience, lid and the lifetime saccade
count in one string, which is what you want when you are standing on the plaza with a laptop
asking why it is staring at the sky. The saccade count is the one to watch: divided by the elapsed
minutes it must stay at or under `SACCADE_BUDGET`, and seeing it climb faster than that on the
real building is the signal that something is wrong with the gaze, not with the taste.

---

## 7. Tests

New file `tests/test_face.py`, in the style of `tests/test_dream.py` and `tests/test_render.py`:
`sys.path.insert` at the top, a couple of small local helpers, render frames and assert on the
numpy array and on timing. No threads, no sleeps, no network.

Helpers:

```python
def _run(face, secs, t0=0.0, visible=True, fps=30):
    """Tick the face for `secs` seconds; return the final t."""

def _draw(face):
    cv = Canvas(); face.draw(cv); return cv.px

def _socket(px, eye):       # the 2x3 sub-array for one eye
def _dark_col(px, eye):     # brightness-weighted centroid column of the *hole* inside a socket
def _lid_line(px, eye):     # the row-4 dash for one eye, as a 3-vector
```

Thirty-six tests. Rendering and geometry:

1. `test_face_lights_the_eye_rows` — tick 1.5 s visible, draw on an empty canvas, assert
   `px[EYE_R0:EYE_R0 + EYE_ROWS, 1:4].max() > 0.2` and the same for the right socket.
2. `test_face_stays_inside_its_band` — after the same draw, `px[FACE_R1 + 1:, :].max() == 0.0` and
   `px[0, :].max() == 0.0`. The body belongs to the up-light.
3. `test_the_bridge_stays_dark` — `px[EYE_R0:EYE_R0 + EYE_ROWS, 4].max() < 0.05`, so the two eyes
   never merge into one band.
4. `test_the_pupil_is_darker_than_the_sclera` — inside each socket, `min < 0.35 * max`.

Aim:

5. `test_pupils_move_toward_the_target` — `look_at` far left, settle, record `face.pupil(0)[1]` and
   `_dark_col(px, 0)`; `look_at` far right, settle, assert both moved right by at least 0.4
   columns. Asserts the maths and the pixels.
6. `test_pupils_look_down_at_the_plaza` — `look_at(row=20.5, col=4, depth=6)`; assert
   `face.pupil(0)[0] > EYE_ROW + 0.3` and that in the rendered socket the lower row is darker than
   the upper one.
7. `test_eyes_converge_on_a_near_point` — define
   `sep = face.pupil(1)[1] - face.pupil(0)[1]`; assert `sep` for a target at depth 6 is at least
   0.15 less than `sep` for the same azimuth at depth 150, and that both are `<= 4.0`.

Calm (§2.0). These are the tests that keep the feature from going wrong:

8. `test_gaze_snaps_and_holds` — sample `face.pupil(0)[1]` every frame through a large target
   change; assert the transit from 10 % to 90 % of the distance takes fewer than
   `(0.28 + 0.05) * fps` frames — the `SACCADE_S` cap plus slack, so a saccade and not a glide —
   and that for the following
   `HOLD_MIN_S` the value changes by less than `0.05` columns per frame (a hold, on drift alone).
9. `test_saccade_rate_never_exceeds_the_budget` — the headline invariant. Drive a `Face` from a
   `Plaza(seed=3, rate_scale=5.0)` at `hour = 17` for 10 simulated minutes, feeding every
   `presence` the sensor would push; assert `face.saccades <= SACCADE_BUDGET * 10 + BUCKET_MAX`
   and that no 60 s window contains more than `SACCADE_BUDGET + BUCKET_MAX`. No startles in this
   test, since startle is explicitly allowed to bypass the bucket.
10. `test_drift_keeps_a_held_gaze_alive_without_flicking` — hold one target for 30 s: assert the
    pupil column is not constant (range > 0.02, so it is alive) and that no single frame moves it
    by more than `0.02` columns (so nothing in the hold is a flick). This is the test that would
    fail if micro-saccades came back.
11. `test_the_eyes_prefer_people_to_cars` — offer a car at road depth and a person on the plaza at
    the same time; assert the person is chosen, and that after the person is established a stream
    of fresh cars never takes the target (`SWITCH_MARGIN` arithmetic of §3.1).
12. `test_pursuit_follows_a_walker_and_loses_a_car` — a presence with `vcol = 0.58` (a walker) is
    tracked with no further saccades for 5 s by dead reckoning alone; a presence with
    `vcol = 4.6` (a car) outruns `PURSUIT_RATE` and the residual error grows, which is the
    intended "the car is lost".

Lids:

13. `test_blink_closes_and_reopens` — `face.blink(t)`; assert `lid` exceeds 0.95 within
    `BLINK_S * 0.6`, that the socket peak at that instant is under `0.35 *` the open peak, and that
    `lid < 0.05` again within `BLINK_S + 0.08`.
14. `test_blinks_happen_on_their_own` — 90 s of ticks with a fixed seed; count `lid` crossings
    above 0.9; assert the count falls inside the band implied by `BLINK_EVERY` and
    `DOUBLE_BLINK_P` (computed from the constants, not hard-coded, so retuning does not break the
    test).
15. `test_drowse_after_a_long_quiet` — 60 s with no presence: assert `state == "drowse"` and
    `lid_bias >= 0.3`; then a presence: assert within 0.4 s `state == "track"` and
    `lid_bias < 0.1`.
16. `test_idle_wander_when_nothing_is_there` — no presence: assert `state` becomes `"scan"` within
    `IDLE_AFTER + 1` and that `face.target` changes at least twice in 30 s (scanning is slow now).
17. `test_dusk_ramp_closes_the_lids` — tick with `sleep` rising 0 → 1 over 12 s: assert `lid`
    tracks it, that the gaze freezes once `lid >= FREEZE_LID` (the pupil offsets stop changing
    beyond drift), and that the rendered socket peak falls below half the open peak.

Sleep and the night (§4.4):

18. `test_face_sleeps_at_night` — replaces the first draft's `test_face_is_absent_at_night`. With
    `sleep = 1.0`: assert `lid > 0.99`, that the socket is gone
    (`_socket(px, 0).max() < 0.05`), and that the lid line is present and non-zero
    (`_lid_line(px, 0).max() > 0.1`). The face is there; its eyes are shut.
19. `test_sleeping_lids_breathe_with_the_body` — sample the lid-line peak across two full
    `NIGHT_BREATH_S` periods; assert it varies by at least 30 % and that its maxima land within
    0.2 s of the maxima of `0.5 + 0.5 * sin(t * 2 * pi / NIGHT_BREATH_S)`, which is the expression
    `_render_night` uses. This is what catches the two constants drifting apart.
20. `test_rem_bulge_moves_under_the_closed_lid` — with `sleep = 1.0, rem = 1.0`, sample
    `_lid_line(px, 0)` over 20 s: assert the argmax of the 3-vector changes at least twice (the
    bulge slides) while the lid stays shut throughout and the total lid-line energy stays within
    10 % of the no-REM case (it redistributes brightness; it does not add any).
21. `test_deep_sleep_is_faint_and_flat` — with `rem = 0.0` the lid line is flat (all three cells
    within 5 % of each other, for the whole run), and at `_sleep_alpha` settled to `DEEP_K` the
    lid-line peak is between `0.3` and `0.8` of its `descent` peak — dimmer, and never gone.
22. `test_the_sleeping_face_never_overwrites_a_dream` — the one that matters. Render a
    `DreamScene` canvas, apply the documented night compositing order (face first, then
    `np.maximum(cv.px, d.px)`), and assert the composite equals the dream-only composite
    everywhere the dream is brighter than the face — i.e. the face contributes only where the
    dream is dark, and after `DREAM_LEAD_S` contributes nothing at all
    (`_sleep_alpha(DREAM_LEAD_S + 0.1) == 0.0`).
23. `test_the_night_loop_has_no_steps_in_it` — walk `_sleep_alpha` through
    `descent → dream → surfacing → deep → descent` with each stage's real minimum duration, and
    assert that the value each stage ends on equals the value the next stage starts on to within
    one frame's worth of that stage's ramp. That is the `DEEP_K` loop of §4.4 checked as a whole
    rather than boundary by boundary, and it is what would fail if a ramp constant were retuned
    without its partner.

Phase integration (constructs the app the way `test_app.py::test_frame_values_in_range` does, then
calls `on_event` and `update` directly):

24. `test_face_is_absent_while_a_performance_plays` — in DAY, push a `spec` event built from
    `validate(LIBRARY["thunderstorm"])`, tick until `app.current is not None`, assert
    `app._face_gate("DAY", 0.0)[0] is False`, and that the eye rows of the rendered canvas are the
    performance's and not the face's (compare against a face-only draw).
25. `test_face_returns_after_the_performance` — then push `{"type": "skip"}`, tick 2.5 s, assert
    `app.face.alpha > 0.8`.
26. `test_thinking_lowers_the_lids_instead_of_hiding` — push `{"type": "text", "text":
    "thunderstorm"}` so `app.pending == 1`; assert the gate returns `(True, 0.8, 0.0)` and that
    after 1 s `app.face.lid > 0.7` while `app.face.alpha > 0.8`. The face is still there, eyes
    lowered.
27. `test_gaze_is_frozen_under_lowered_lids` — with the gate at `sleep = 0.8`, move the target
    across the plaza and assert `face.saccades` does not increase and the pupil offsets change by
    less than drift.
28. `test_an_onsite_prompt_makes_it_look_down` — push a `spec` event with `source: "pedestal"`,
    tick, assert `app.face.target[0] > 19` and `app.face.target_kind == "pedestal"`; then tick 12 s
    with the gate hidden and assert the target has **not** expired (the frozen-age rule of §4.1).
29. `test_mouse_moves_the_eyes` — push `{"type": "mouse", "over": True, "r": 3, "c": 8}`, tick,
    assert both pupils moved right; push `{"type": "mouse", "over": False}` and assert the state
    returns to `scan` within `IDLE_AFTER + 1`.
30. `test_the_eyes_open_at_dawn_and_shut_at_night` — the arc of §4.0 end to end. Drive the app
    through `dawn → day → dusk → night → dawn` with phase overrides and assert, at each stage, the
    lid values from the §4.0 table: shut in DAWN, open in DAY, shut by `prog 0.3` of DUSK, shut
    all night, and open again after the next `_enter("DAY")`. One test, five assertions, and it is
    the one that would catch a regression in any single phase hook.

Traffic:

31. `test_plaza_is_deterministic` — two `Plaza(seed=5)` stepped 600 times at `dt = 1/8` with
    `hour = 12`; assert the sequences of `(salient id, round(col, 3))` are identical, and that
    `Plaza(seed=6)` differs. Random-looking, reproducible.
32. `test_plaza_produces_traffic_that_crosses_and_leaves` — at `hour = 17`, 120 simulated seconds:
    at least 5 agents spawn, every agent's `col` moves monotonically in one direction, no agent
    lives longer than `MAX_LIFE`, and `len(plaza) <= MAX_AGENTS` throughout.
33. `test_rates_follow_the_hour_coarsely` — 300 s at `hour = 3` spawns strictly fewer agents than
    300 s at `hour = 17`, with the same seed. Only the ordering is asserted, never a count: the
    rate table is allowed to be retuned without breaking a test.
34. `test_most_cars_are_never_offered` — over 600 s at `hour = 17`, the fraction of spawned cars
    that `salient()` ever returns is at most `2 * CAR_LOOK_P`, and at least one car is returned
    (it does watch the occasional car).
35. `test_presence_events_have_the_shape_and_the_hysteresis` — drive `TrafficSensor._tick()`
    directly 200 times against an `InputBus()` (no thread, no sleep); assert every event has
    `type == "presence"` and carries `row`/`col`/`depth`/`kind`/`salience`/`id`, that `row > 13`,
    and that the push rate is near `1 / PUSH_EVERY` rather than one per tick. Then hand-build two
    agents at salience 0.50 and 0.80 and assert `salient()` does not switch (`SWITCH_MARGIN =
    0.35`), and does switch at 0.90.

Cost:

36. `test_face_is_cheap` — 600 `update` + `draw` pairs in under 0.5 s, in the spirit of
    `test_keeps_up_with_30fps`.

Existing tests must stay green untouched: `python -m pytest -q`, plus
`python main.py --demo --offline --duration 30 --display null` before finishing each commit.

---

## 8. Risks

**No design questions are open.** A face is wanted; it sleeps at night; the mouth ships on; DAWN's
two blinks stay on the whole body; deep sleep keeps a faint lid line. What follows is the list of
things that can still go wrong once it is built, and what to do about each.

### 8.1 The aesthetic risk

The remaining risk is legibility, not concept: two lit blocks and a dash at the top of a tower can
read as a jack-o'-lantern rather than as a face. Everything that walks it back is a constant —
`SCLERA_K` down from 0.55, `MOUTH_K = 0.0` to drop the mouth entirely, and `NIGHT_LID_K` down if
the sleeping dashes read as two stuck windows. **Ashrit should see slice 2 on the simulator, and slice 3 (the sleeping face)
on the hosted `?view=street` instance, before the traffic slice lands**, because a street view at
distance is the only honest test of whether any of it reads.

### 8.2 Row 0 and daylight (already flagged in HANDOFF §6 and §7.4)

If row 0 is not the top on the real driver, the face is at the bottom of the tower and the
up-light is at the top. The calibration pattern from §8.7 of HANDOFF must run before the face is
shown to anyone. Separately, HANDOFF §7.4 records that in daylight the windows read faintly at
best — and the face is a DAY-phase behaviour, so on Sept 29 it may be invisible exactly when it is
running.

This is now less sharp than it was, because the face is no longer a DAY-only behaviour: the
sleeping face runs all night, which is when the windows read best and when the Sept 29 audience
will be standing there. The DUSK ramp (§4.3) and the sleeping dashes (§4.4) cover the moment the
crowd is actually present — the eyelids come down in front of them and then the building dreams —
so nothing extra is needed for the show.

### 8.3 What the eyes are, and what to say about them

Nothing is watching. That is the design (§3), and it makes disclosure more important rather than
less, because the eyes will be convincing. Two places, and the wording should be this plain:

- **`/journal`**, one line under the heading: *"The eyes are not a camera. Nothing is watching you.
  The building guesses at the traffic below from the time of day, and looks where it guesses."*
- **At the pedestal**, on whatever card or screen is printed: the same two sentences, shortened —
  *"No camera. The building is guessing."*

If a sensor is ever added, that line has to change in the same commit as the sensor: say what it
sees, that no image is stored, and that the only thing leaving the sensor is one
`(row, col, depth, salience)` tuple. Writing the disclosure now, while it is easy, is what makes
that rule enforceable later.

### 8.4 Photosensitivity

A blink changes about 12 windows by roughly 0.6 in 0.12 s, a mean-brightness swing near 0.05,
comfortably under `--gentle`'s 0.12-per-frame cap; blinks are never closer together than 0.22 s and
the eyes are hidden during flashes (which only happen inside performances). The calm retuning of
§2.0 makes this strictly better than the first draft — fewer saccades, fewer gaze-evoked blinks —
and the sleeping face changes nothing fast at all. Confirm once with `--gentle --stats` on a long
idle run, because the face is still the first thing that changes a block of windows quickly while
the building is otherwise still.

### 8.5 The one coupling to watch

`NIGHT_BREATH_S = 8.0` in `face.py` must equal the `8.0` inside `_render_night`'s
`b = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 8.0)`. They are duplicated rather than shared because
importing app state into `face.py` would invert the dependency for one float. Test 19 asserts they
agree by comparing maxima, so a divergence fails loudly instead of showing up as a face that
breathes out of step with the tower it is on.

---

## 9. Work, smallest shippable slice first

**Nothing here is built. This is a plan awaiting approval**; no file in the repository has changed
except this one. The slices below are the order to build in once it is approved, smallest
shippable piece first, each one a commit that leaves the repository working.

- [ ] **1. `face.py` and its unit tests.** Constants, `Face`, the socket / pupil / lid / lid-line
      masks, the budgeted saccade machine, blinks, scan and drowse. No `app.py` changes; nothing
      visible yet. Tests 1–17 and 36. Verifies the geometry of §1.3 and — more importantly — the
      calm invariants of §2.0 against real pixels before anything is wired to the building.
- [ ] **2. Wire the waking face into `app.py`.** `_face_gate()`, the `Face.update` call in
      `update()`, the `draw` call at the end of `_idle_awake` replacing the wandering blob, the
      `_enter` hooks for DAWN and DAY, `--no-face`, and the face line in the status panel. Tests
      24–27. **Ship point:** the building has a face in DAY that blinks, looks around slowly by
      itself, lowers its lids while it thinks, and closes them through dusk. Show this to Ashrit
      on the simulator (§8.1) before going further.
- [ ] **3. The sleeping face at night.** `Face.sleep_now()`, the `SLEEP` state, the breathing lid
      line, the REM bulge, `_sleep_alpha()`, the `_enter("NIGHT")` hook and the single `draw` call
      in `_render_night` above the stage machine. Tests 18–23 and 30. **Ship point:** the arc of
      §4.0 is complete — the eyes open at dawn, watch all day, close through dusk, and breathe
      shut all night with a bulge sliding under the lids while it dreams. This is its own slice
      because it is the half of the feature that touches the night renderer, and because test 22
      (never overwrite a dream) is the one regression that would actually spoil the piece.
- [ ] **4. Pointer presence.** `mouse` / `touch` handled in `on_event`, `Face.pointer`,
      `Face.startle`, the look-here and blink buttons, the note in the control panel, and two
      demo-timeline events. Tests 5–8, 29. **Ship point:** the eyes follow your cursor in the
      simulator, which is the thing that makes people believe it.
- [ ] **5. `sensors/traffic.py`.** `Plaza`, `TrafficSensor`, `CAR_LOOK_P`, the `presence` branch in
      `on_event`, the rate slider, `--no-traffic`, the hour hand-off, the traffic count in the
      status panel. Tests 9, 11, 12, 31–35. **Ship point:** with no input at all the eyes rest on
      plausible passers-by, thickening at rush hour, at a bounded number of saccades a minute.
- [ ] **6. On-site presence.** The `ONSITE`-gated pedestal look in the `spec` branch and the
      frozen presence age while hidden, so the building looks down at whoever just spoke to it
      once its performance of their prompt finishes. Test 28.
- [ ] **7. Expression polish (optional).** One item: mouth curvature driven by the last performed
      spec's `mood.valence`, decaying back to `MOUTH_CURVE0` over 60 s, so the face carries a trace
      of what it was last asked to become. Everything else once listed here is decided and built
      into the slices above.
- [ ] **8. Documentation and the disclosure line.** The "wandering gaze" line in `README.md`; a
      status row and a `presence` row in `HANDOFF.md` §1 and §4, plus a note that `mouse`/`touch`
      are no longer ignored; and the §8.3 disclosure text on `/journal` — that one ships with
      slice 5, not after it, because slice 5 is where the eyes start looking convincing.

Each commit finishes with `python -m pytest -q` green and
`python main.py --demo --offline --duration 30 --display null` running clean. Nothing here touches
`utilities/`, `tetris.py`, `scene.SCHEMA` or `validate()`; no `Color` is mutated; no work happens
in `update()` except numpy arithmetic; the only new thread pushes `presence` events onto
`common.inputs.BUS` and does nothing else.
