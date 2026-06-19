# eactgen — CASIO eActivity generator

*[Versión en español](README.es.md)*

Generate CASIO **eActivity** files (`.g2e` / `.g1e`) for fx-9860G–series graphing
calculators directly on your computer — write your formulas in plain text with a small
LaTeX-like markup and get a file you can transfer to the calculator.

It's a clean-room, local recreation of the online
[EactMaker](https://tools.planet-casio.com/EactMaker/) tool: the eActivity binary
format was reverse-engineered from real EactMaker output, and the generator reproduces
that output **byte-for-byte** (11/11 sample files, 61/61 content lines verified).

No dependencies — just Python 3 and the bundled `chars.toml` character table
(from the [Cahute](https://cahute.org) project, CeCILL 2.1).

## Why

The calculator doesn't store text as Unicode; it uses CASIO's own *FONTCHARACTER*
encoding (nabla, Greek letters, superscripts, fractions, integrals…). Typing those on
the device is painful. This tool lets you author on a real keyboard and produces a valid
file the calculator opens.

> **Extensions.** The fx-9860G**III** opens **both `.g1e` and `.g2e`** — the two
> containers are byte-structurally identical; only the extension differs (`.g2e` is the
> native format for the GII/GIII, `.g1e` is the older fx-9860G format). `.g2e` is the
> safe default. If a file won't open, the cause is the *contents*, not the extension.

## Install

```bash
git clone <repo-url> eactgen && cd eactgen
# Python 3, no extra packages needed
```

## Usage

Write one eActivity line per row in a UTF-8 text file (`notes.txt`):

```
∇²V=0
E=-∇V
We=½CV²=\int{}{x=V}{½εE²}dV
\int{}{C}{E·dl}=0
J=[A/m²]
ρ_v=\frac{Q_e}{ε₀}
```

Generate the file:

```bash
python3 casio_translate.py build notes.txt --title PHYS -o PHYS.g2e
```

- `--title` (≤8 chars) becomes the `======PHYS======` banner shown as the first line.
- The **on-calculator name comes from the output file name** (`PHYS.g2e` → "PHYS",
  ≤8 chars, uppercased). It is *not* stored inside the file.

Then copy `PHYS.g2e` to the calculator (USB mass storage / Link / FA-124) and open it
from the eActivity menu.

### Other commands

```bash
python3 casio_translate.py encode "∇²V=0"               # show CASIO bytes (hex)
python3 casio_translate.py decode-hex "d8 a8 1a 32 1b"  # bytes -> readable text
python3 casio_translate.py inspect FILE.g2e             # header check + decoded text
```

## Markup

| You write | Result |
|-----------|--------|
| `\frac{a}{b}` | stacked fraction |
| `½ ⅓ ¼ …` | stacked fraction (vulgar-fraction glyphs) |
| `\sqrt{x}` | square root |
| `\abs{x}` | absolute value / modulus |
| `\int{lo}{hi}{f}` | integral (any arg may be empty: `\int{}{x=V}{f}`) |
| `\log{a}{b}` | log base *a* of *b* |
| `\sum{n}{k}{0}{a}` | sum (count, variable, start, expression) |
| `\mat{a&b}{c&d}` | matrix (rows in `{}`, cells split by `&`) |
| `\diff{a}{b}` / `\diff2{a}{b}` | 1st / 2nd derivative of *a* in *b* |
| `\note{title}{body}` | note / memo strip (own line) |
| `^2`, `^{n+1}` | superscript / power |
| `_v`, `_{12}` | subscript (letters and digits) |
| `²` `³` | superscript glyphs |
| `∇ ∂ · ⇒ ε μ π σ ρ θ Ω …` | typed directly as Unicode |
| `\nabla \partial \epsilon \pi \sigma …` | LaTeX names, if easier to type |

Plain ASCII passes through unchanged. This matches EactMaker's markup exactly — every
sample file regenerates byte-for-byte.

## Limitations

- An empty note body (`\note{T}{}`) is degenerate in EactMaker — give notes a body.
- Verified on the fx-9860G family `.g2e`/`.g1e`. fx-CG (Prizm) `.g3e` is *not* targeted.

## How it works

See [`AGENTS.md`](AGENTS.md) for the full reverse-engineered format: standard header and
checksums, the MCS directory, cell layout, and the complete markup→bytes mapping. The
implementation is a single file, `casio_translate.py`.

## Credits

- Character table: the [Cahute](https://cahute.org) project (Thomas Touhey), CeCILL 2.1.
- Format inspired by / verified against [EactMaker](https://tools.planet-casio.com/EactMaker/)
  by Helder7 and Ziqumu, and SimonLothar's reverse-engineering work.

## Disclaimer

CASIO and fx-9860G are trademarks of CASIO Computer Co., Ltd. This is an independent,
unofficial tool. Keep backups of files on your calculator.
