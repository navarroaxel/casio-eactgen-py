# AGENTS.md — CASIO eActivity generator

Instructions for AI agents working in this repo.

## What this project is

A local recreation of **EactMaker** (`tools.planet-casio.com/EactMaker/`, a server-side
tool whose source isn't public). It converts Unicode text + LaTeX-ish markup into
CASIO **eActivity** files (`.g2e` / `.g1e` / `.g3e`) for graphing calculators, doing both the
character encoding (Unicode → CASIO FONTCHARACTER) and the binary container.

The whole implementation is one file: **`casio_translate.py`** (stdlib only, Python 3).
It loads the character table from **`chars.toml`** (from the Cahute project, CeCILL 2.1).

### Target hardware
The user's calculator is an **fx-9860GIII**, which opens **both `.g1e` and `.g2e`**. The
two containers are byte-structurally identical (verified); only the extension differs
(`.g2e` = native GII/GIII format, `.g1e` = older fx-9860G). Default to `.g2e`. The
extension is **not** why a file fails to load — that's always the contents.

`.g3e` (fx-CG / Prizm) is also supported via `build --format g3e`. It is the `.g2e`
container with a fixed prefix subtype block changed (`_FMT_OVERRIDES`), reverse-engineered
byte-for-byte from the live server — *not* the large fx-CG subheader the old TASK.md
predicted. (The live server's real `.g1e` also uses a distinct subtype block, but we keep
`.g1e` == `.g2e` bytes by design; see `_FMT_OVERRIDES`.)

## Ground truth / how to validate

Never trust a hand-derived format rule — verify byte-for-byte against the real samples:

- `examples/*.g2e` — real EactMaker output (the oracle).
- `input.txt` — the markup inputs that produced them (UTF-8; sections of formula lines).

Two invariants the code must always satisfy (run these after any change):

```python
# 1) Container: rebuild every example from its own parsed cells -> byte-identical (11/11)
# 2) Markup: every input.txt line that maps to a cell -> encode() reproduces it (61/61)
```

If you change `encode()`, `build_eact()`, `fix_header()`, or `_EACT_PREFIX`, re-run the
round-trip and the per-cell markup check (see the validation snippets used in git history /
prior session, or write equivalents). A regression shows up as a non-identical example.

## CLI

```bash
python3 casio_translate.py build text.txt --title NAME -o out.g2e   # main use
python3 casio_translate.py encode "∇²V=0"                            # text -> hex bytes
python3 casio_translate.py decode-hex "d8 a8 1a 32 1b ..."           # bytes -> text
python3 casio_translate.py inspect out.g2e                           # header + decoded text
```
`text.txt` = one eActivity line per row, using the markup below (same dialect as `input.txt`).

## File format (reverse-engineered, verified)

Standard header (0x00–0x67 is a fixed prefix, `_EACT_PREFIX`; these fields are patched):
- `0x20` u32 BE = filesize; `0x10` u32 BE = ~filesize
- `0x0E` = `~(size+0x41) & 0xFF`; `0x0F` = `0xFE` (constant)
- `0x14` = `(0x147 - size) & 0xFF`

MCS / directory:
- `@EACT` entry offset `0x74` = `size - 0x78`; `EACT1` entry offset `0x84` = `size - 0x8C`
- line count u32 BE at `0x8C`; directory entries start `0x90`, 4 bytes each:
  `type(1) + u24 offset`, **offset measured from base `0x8C`**.

Cells (contiguous after directory + `00 00 00 00`):
- type `0x07` = title banner `"="*6 + title.ljust(8) + "="*7`
- type `0x81` = normal line; type `0x06` = `\note` (nested @EACT — **not yet supported**)
- `cell = content + 0x00 + zero-pad to 4-byte boundary` (note cells get +4 extra zeros)

## Markup → bytes

All 12 EactMaker constructs are implemented and verified byte-identical:

- `\frac{a}{b}` → `bb 1d 1a a 1b 1a b 1b 1e`
- `\sqrt{x}`    → `86 1d 1a x 1b 1e`
- `\abs{x}`     → `97 1d 1a x 1b 1e`
- `\int{A}{B}{C}` → `8d 1a C 1c B 1c A 1b`  (integrand C first)
- `\log{a}{b}` → `7f85 1a a 1c b 1b`
- `\diff{a}{b}` → `7f26 …`; `\diff2{a}{b}` → `7f27 …`  (form `op 1a a 1c b 1b`)
- `\sum{n}{k}{s}{e}` → `7f29 1a e 1c k 1c s 1c n 1b`  (expr, var, start, count)
- `\mat{a&b}{c&d}` → `7f5d a4 (a4 cell 1c cell b4)… b4`
- `\note{title}{body}` → **type 0x06 cell** = nested `@RUNMAT`/`TEXT1` sub-container;
  see `build_note_content()` (note title and body are themselves `encode()`d).
- `^x` / `^{...}` → `a8 1a x 1b` (power)
- `_d` (digit)   → `e5 (d0+d)`;  `_L` (letter) → `e7 |ord(L)` (Mini Latin)
- `∇` → `e6da`, `+` → `89`, `\bolde;` → `e5b0` (ℇ), `·`→`e5a7`, `∂`→`e6b9`, `⇒`→`13`
- Printable ASCII (0x20–0x7E) → itself (EactMaker does NOT use fontchar codes for ASCII)
- Greek small α–ω = `e640`–`e658`, capitals `e540`–`e558`; `²`=`e5c2`, `³`=`e5c3`
- Vulgar fractions (`½` …) expand to stacked fractions; subscripts/superscripts recurse

`EACT_OVERRIDE` (in code) holds the chars EactMaker encodes differently from the table.
The full feature set (and the per-construct `\xxx` insert templates) comes from the
site's own config: `formats/g2e.js` (`GuiConfig.ButtonsBottom` + `CharsTables`).

These were reverse-engineered by probing the live server with synthetic inputs and
diffing the output (`POST` to `system/converter.php` with `titre`/`format`/`font`/`texte`).
Validation: **9/9** files in `input.txt` regenerate byte-identical; container round-trip 11/11.

## Conventions

- Match EactMaker's bytes exactly — it's the spec. When uncertain, decode an example and copy.
- Keep everything in `casio_translate.py`; load tables from `chars.toml` (don't hardcode the table).
- Don't add dependencies; stdlib only.
- The format spec also lives in the module docstrings and in the project memory
  (`eactmaker-recreation.md`).

## Known limitations / next steps

- An **empty note body** (`\note{T}{}`) is degenerate in EactMaker (no 0x06 cell). Avoid it.
- The Cyrillic char table (in `g2e.js`) isn't specially handled, but those chars resolve
  through `chars.toml` like any other.
- CILIND.g2e / TDCF.g2e have no matching lines in `input.txt`, so they can't be regenerated
  from it (not a bug — just absent source).
