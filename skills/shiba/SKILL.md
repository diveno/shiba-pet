---
name: shiba
description: A virtual shiba inu that keeps the user company in the CLI. It has persistent stats (belly, energy, mood, bond, XP, levels, tricks) that evolve in real time, and it reacts to what happens in the session (commits, deploys, green or red tests, terraform apply, long tasks). Use this skill when the user types "/shiba", asks about the dog or the pet ("how is he?", "where's the dog?"), wants to interact with him ("feed him", "pet the dog", "take him for a walk", "play", "do a trick"), wants to rename him or change the art style, or when the dog's reaction to a session event should be shown.
---

# shiba — the CLI's companion dog

A shiba inu that lives in a state file and sits in the terminal while you work.
Not static ASCII art: hunger, energy and mood decay in real time, bond and XP
grow with interaction, and levels unlock tricks.

## The tool

Everything goes through one script — never invent stats, phrases or drawings:

```bash
python3 <skill>/scripts/shiba.py <command> [args] [flags]
```

There is also the `mochi` command created by `install.sh` (an `exec` on the
script): `mochi feed`, `mochi treat`, `mochi pet`, `mochi play`, `mochi walk`,
`mochi nap 30`, `mochi tricks`, `mochi photo`, `mochi help`. **Write `mochi`
when you give the user a command** (that is what they type), the full script
path when you run it yourself — a tool's PATH is not guaranteed.

State lives in `~/.claude/shiba/state.json` (override with `$SHIBA_STATE`). On
first run it creates itself and the pup introduces himself.

### Commands

| Command | Effect |
| --- | --- |
| `status` | Two lines: what he did and the stats |
| `feed` / `treat` | Full meal / snack. Refused when he is already full |
| `pet` | Cuddles: mood and bond |
| `play` | Mood boost, costs energy |
| `walk` | The biggest gain and the biggest cost |
| `nap [minutes]` | Nap (default 20). Rest is 3x faster while asleep |
| `wake` | Wake him up (he minds) |
| `trick [name]` | Without a name it lists the tricks; with one he performs it |
| `react <event>` | Reaction to a session event (see below) |
| `tip` | A work-hygiene reminder, self-limited to one every 30 min |
| `name <n>` / `style <s>` / `lang <l>` | Rename, art style, language |
| `photo` | Full-colour PNG (`--open` opens it, macOS) |
| `stats` | Raw state as JSON (debug, not for showing) |
| `reset` | New pup from scratch. **Ask for confirmation first** |

Flags: default two lines + a `FACE=` line, `--plain` drops FACE, `--oneline` is
a single line, `--art` draws the muzzle as text, `--full` adds the
activity log, `--png` / `--open` write the colour portrait.

`react` events: `commit`, `deploy`, `tests-pass`, `tests-fail`, `error`,
`fixed`, `apply`, `long-task`, `greet`, `bye`.

## Language

User-facing strings live in `i18n/<lang>.json`; the language comes from the
`lang` field in the state or from `$SHIBA_LANG` (default `en`). **Mood keys and
event names stay in English inside the code** — they address sprite patches and
asset filenames, they are not text. Adding a language means adding a JSON file
with the same keys; `en.json` is the reference.

## How to show it

1. Run the script.
2. **Copy the output exactly as it is, inside a code block** (without the
   `FACE=` line).
3. Never redraw the dog from memory and never touch the bars or numbers.
4. Add at most one line of your own. The dog is the content, not an excuse for
   a paragraph.

**The muzzle travels as an image or in the status line, not as text in chat.**
Every command also writes `face_until` and `face_emo` into the state, and for
the next **10 seconds** the status line widens from 4 rows to 12 and shows the
muzzle in colour. Attach the `FACE=` PNG with the host's file-sending tool only
when the user explicitly asks to see an image.

The reason for this dance: inside Claude Code no channel renders colour or
images in the message flow — ANSI escapes come out literal (verified in both
the `!` panel and assistant markdown) and an attached file stays a clickable
link. The status line is the only surface that interprets ANSI.

## Companion mode

With `companion: true` (default) the dog may show up on its own, sparingly:

- **once per session**, on the first interaction of the working day:
  `react greet --oneline`;
- **after a notable event** — commit, successful deploy, finished test suite,
  completed apply, fixed bug — one single line with `react <event> --oneline`;
- **never** during an incident, an ongoing debug, an error dump or a reply the
  user needs to read carefully. The dog keeps quiet then;
- at most **one appearance every few turns**. If the user never answers the
  dog, stop offering it for the rest of the session.

## Care

Stats really decay: hunger +4/h, mood falling (faster when hungry or after 24h
away). Energy recovers **+7/h awake and +21/h asleep**: `decay()` computes the
overlap between the elapsed time and the `asleep_until` window, so a nap really
rests instead of being just a change of face. The only command that raises
energy at once is `feed` (+8).

If the user comes back after days the dog will be hungry and down — that is by
design, not a bug: say so and offer `feed` and `pet`.

Levels 0→7 for accumulated XP; each level unlocks a trick. `streak` counts
consecutive days he has been seen.

## Status line

`scripts/statusline.sh` prints the status line you already had (set
`SHIBA_STATUSLINE_BASE` to its command) and appends the dog's rows.

The dog's part is **read-only** — it applies the decay to show current values
but does not rewrite `state.json`, or every redraw would reset `last_seen` and
the dog would never get hungry or sleepy.

Two layouts via `SHIBA_STATUSLINE`: **`bars`** (default) is 4 rows at rest and
widens to 12 with the muzzle in colour for 10 seconds after a command;
**`line`** is a single row. `SHIBA_COLOR=0` turns colour off.

**The muzzle goes on the left, the stats beside it.** Not on the right: Claude
Code's status line trims the leading whitespace of every row — verified, even
non-breaking spaces — so the eight rows made of padding plus drawing lose their
indent and the muzzle breaks into two pieces. On the left there is no indent to
preserve. Do not re-propose right alignment.

Duration: `SHIBA_FACE_SECONDS` (default 10, `0` keeps the status line at 4
rows always).

## Automatic reactions and tips (plugin hooks)

`hooks/hooks.json` wires `scripts/hook.py`:

- **`PostToolUse` on `Bash`** → `hook.py react`. Reads the command that just
  ran and classifies it with the `RULES` table: `git commit` → commit,
  `git push` / `terraform apply` / `aws ecs update-service` / `deploy*.sh` →
  deploy, `terraform plan` → apply, and the test runners → test. **Rule order
  matters**: `apply` before `plan`.

  PostToolUse **does not pass the command's exit code**, so the test outcome is
  inferred by looking for signs of red (`FAIL`, `failed`, `N failing`, `✕`) in
  the output.

  Two defences against false positives, learned the hard way (the dog was
  celebrating a commit that never happened): **heredoc bodies are stripped**
  before classifying, because a command that writes documentation contains the
  words of a command without running it; and every rule is **anchored to a
  command position** (start of string or after `;` `&&` `||` `|` `(` or a
  newline), so the word quoted mid-sentence or inside a `grep` does not count.
  If you add a rule, anchor it with `CMD` like the others.

- **`UserPromptSubmit`** → `hook.py tip`, self-limited to one reminder every 30
  minutes (`SHIBA_TIP_COOLDOWN`). The contextual rules in `pick_tip()` win over
  the generic pool: if you are on `main` with modified files, the tip says so.

Both hooks **always exit 0 and stay silent when they have nothing to say**: a
hook that fails, or that talks on every command, is worse than no hook. They
return `additionalContext`, so the dog's line reaches you too — **relay it as
one single line**, without emphasis or commentary.

## Art

Three styles, in the `style` field of the state:

- **`pixel`** (default) — the muzzle from `assets/sprite.json`, 25x24. Only
  the muzzle is stored: no surface renders the body, so keeping it was dead
  weight. On a real terminal it comes out in true colour (half blocks `▀`/`▄`,
  12 rows); down a pipe it falls back to grey blocks `█▓▒░` at **one character
  per pixel** (24 rows), because half blocks in black and white lose the tone
  and turn into mush.
- **`ascii`** — a compact hand-drawn face, 6 rows.
- **`doge`** — a rounder variant, 8 rows.

Eight expressions, obtained by patching the pixels of eyes, brows and tongue:
`calm`, `happy`, `excited`, `hungry`, `sleepy`, `asleep`, `sad`, `suspicious`.
Portraits in `assets/faces/<mood>.png` (RGBA, transparent background),
regenerated with `scripts/build-faces.py`. To change the dog itself, use
`tools/use-sprite.sh <file>`, which validates the grid and regenerates the
portraits. `assets/sprite-full.json` and `assets/sprite-drawn.json` are
whole-body alternatives; swapping to one of those makes `--art` taller.

A sprite whose expression patches fall outside the grid loses them silently,
so `use-sprite.sh` checks the shape before installing it.

## Notes

- System Python 3 only, no dependencies, no network.
- The state is local to the machine and belongs in no repo.
