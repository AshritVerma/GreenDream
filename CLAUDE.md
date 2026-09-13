# GreenDream — agent notes

Read `HANDOFF.md` first: it has the full context (what exists, how it runs, the event vocabulary,
the scene-spec and dream-script schemas, decisions already made, and the prioritized backlog).

Hard rules for this codebase:
- The only building contract is `utilities/display.py` (`Frame`, `Color`, `Display.send` at ≤ 30 fps). Never edit `utilities/` or `tetris.py`.
- Never mutate a `Color`; assign new ones. Row 0 is the top of the building.
- `App.update()` must return every frame — no sleeps or blocking I/O in the frame loop; put work on threads that push events onto `common.inputs.BUS`.
- The model never draws pixels: new visuals = a new field in `scene.SCHEMA` + renderer support + a `validate()` rule.
- Raw user text is never displayed on the facade; only the validated `word` (A–Z ! ?, ≤ 7 chars).
- Keep `python -m pytest -q` green and `python main.py --demo --offline --duration 30 --display null` running before you finish a change.
- Never commit secrets (`ANTHROPIC_API_KEY`, the hack event password). The simulator instance name `olive-koala` is fine to reference.
- Git: pull first, summarize what was done, wait for Ashrit's explicit approval before pushing.
