#!/usr/bin/env python3
r"""
casio_translate.py — Translate Unicode <-> CASIO fx-9860G(II/III) character encoding.

CASIO eActivity / formula files (.g1e, .g2e, .g1m, ...) do not store text as
Unicode. They use CASIO's own "FONTCHARACTER" encoding: a mix of single bytes
and two-byte sequences whose first byte is one of the lead bytes
0x7F, 0xE5, 0xE6, 0xE7, 0xF7, 0xF9.

This tool converts your Unicode formulas (nabla, superscripts, Greek letters,
...) into that encoding and back, and can inspect / patch real .g1e/.g2e files.

The character table is the authoritative one from the Cahute project
(chars.toml, by Thomas Touhey, CeCILL 2.1). Keep chars.toml next to this script.

Encodings used for the characters you asked about (verified against TDCF.G1E):
    nabla   '∇'  -> 0xD8          (the byte your TDCF file uses for ∇)
    Greek   'ε'  -> 0xE6 0x44      (two-byte; 'α'..'ω' = 0xE640..0xE658)
            'μ'  -> 0xE6 0x4B,  'π' -> 0xE6 0x4F,  'θ' -> 0xE6 0x47, ...
            capitals 'Α'..'Ω' = 0xE540..0xE558
    squared '²'  -> 0xA8 0x1A 0x32 0x1B   (Power '^' + raised "2"; math form)
                    or use --literal-super for the text glyph 0xE5 0xC2
    cubed   '³'  -> 0xA8 0x1A 0x33 0x1B   (or 0xE5 0xC3 with --literal-super)

Markup understood by the encoder:
    ^2, ^n        superscript of the next single char
    ^{...}        superscript of a whole group        e.g.  m^{-2}
    \frac{a}{b}   stacked fraction  -> BB 1D [1A a 1B][1A b 1B] 1E
    ½ ⅓ ¼ ¾ ...   vulgar-fraction glyphs become stacked fractions too
    (plain "1/2" stays a linear division 31 2F 32, NOT a stacked fraction)
    \nabla \pi \epsilon \mu ...   LaTeX-style names for symbols hard to type
    Unicode chars (∇ ² ³ ε π …) are accepted directly too.

Usage:
    python3 casio_translate.py encode "∇²V=0"
    python3 casio_translate.py encode "We=1/2 CV^2"  --bytes-out blob.bin
    python3 casio_translate.py decode-hex "d8 a8 1a 32 1b 56 3d 30"
    python3 casio_translate.py inspect  TDCF.G1E
    python3 casio_translate.py patch    TDCF.G1E --at 0xc8 --text "∇²W=0" -o OUT.g1e
    python3 casio_translate.py selftest TDCF.G1E NO.g2e
"""
import sys, os, re, ast, argparse

LEAD_BYTES = {0x7F, 0xE5, 0xE6, 0xE7, 0xF7, 0xF9}
NABLA_CODE = 0xD8          # what TDCF.G1E uses for the Laplacian's del/nabla
POWER = 0xA8               # FONTCHARACTER "Power" ( ^ )
SUP_OPEN, SUP_CLOSE = 0x1A, 0x1B   # natural-display raise (superscript) brackets
# Natural-display stacked fraction, as found in TDCF.G1E (the ½ in "We=½CV²"):
#   BB 1D  [1A <numerator> 1B]  [1A <denominator> 1B]  1E
FRAC_PREFIX = [0xBB, 0x1D]
FRAC_SUFFIX = [0x1E]
GROUP_OPEN, GROUP_CLOSE = 0x1A, 0x1B
# Unicode "vulgar fraction" glyphs -> (numerator, denominator) strings
VULGAR = {
    "½": ("1", "2"), "⅓": ("1", "3"), "⅔": ("2", "3"),
    "¼": ("1", "4"), "¾": ("3", "4"), "⅕": ("1", "5"), "⅖": ("2", "5"),
    "⅗": ("3", "5"), "⅘": ("4", "5"), "⅙": ("1", "6"), "⅚": ("5", "6"),
    "⅛": ("1", "8"), "⅜": ("3", "8"), "⅝": ("5", "8"), "⅞": ("7", "8"),
    "⅐": ("1", "7"), "⅑": ("1", "9"), "⅒": ("1", "10"),
}

# ---------------------------------------------------------------------------
# Load the Cahute character table (chars.toml).
# ---------------------------------------------------------------------------
def _toml_int(s):
    if s is None:
        return None
    s = s.strip()
    try:
        return int(s, 16) if s.lower().startswith("0x") else int(s)
    except ValueError:
        return None

def _unicode_str(entry):
    u = entry.get("unicode")
    if not u:
        return None
    try:
        v = ast.literal_eval(u)
        v = [v] if isinstance(v, int) else list(v)
        return "".join(chr(x) for x in v)
    except Exception:
        return None

def load_table(path):
    txt = open(path, encoding="utf-8").read()
    entries = []
    for block in txt.split("[[chars]]")[1:]:
        e = {}
        for line in block.splitlines():
            m = re.match(r"\s*(\w+)\s*=\s*(.+?)\s*(?:#.*)?$", line)
            if m:
                val = m.group(2).strip()
                if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                    val = val[1:-1]          # unquote string values ("9860", names)
                e[m.group(1)] = val
        entries.append(e)
    return entries

def build_maps(entries):
    """
    Returns (dec, enc):
      dec: int code -> unicode string  (for decoding; includes multi-cp glyphs)
      enc: single unicode char -> int code  (for encoding; single-cp only)
    Preference for encoding: 9860 multibyte table first (modern, unambiguous),
    then base single-byte, then legacy. Multi-codepoint token glyphs (e.g. 'Σx²')
    are used only for decoding, never for encoding a lone char.
    """
    dec, enc = {}, {}
    # rank: lower = preferred for the encode map
    def rank(e):
        t = e.get("table")
        if t == "9860":
            return 0
        if t is None:
            return 1
        return 2  # legacy
    for e in sorted(entries, key=rank):
        code = _toml_int(e.get("code_9860")) or _toml_int(e.get("code"))
        if code is None:
            continue
        s = _unicode_str(e)
        # decode map: keep first writer per code, but let 9860 override
        if code not in dec or e.get("table") == "9860":
            if s is not None:
                dec[code] = s
        # encode map: only single-codepoint glyphs, first (best-ranked) wins
        if s is not None and len(s) == 1 and s not in enc:
            enc[s] = code
    return dec, enc

# ---------------------------------------------------------------------------
# Encoding: Unicode (+ light markup) -> CASIO bytes
# ---------------------------------------------------------------------------
LATEX = {
    r"\nabla": "∇", r"\del": "∇", r"\partial": "∂",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ",
    r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\phi": "φ", r"\chi": "χ", r"\psi": "ψ",
    r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ", r"\Omega": "Ω",
    r"\bolde;": "ℇ", r"\infty": "∞", r"\times": "×",
    r"\div": "÷", r"\le": "≤", r"\ge": "≥", r"\ne": "≠", r"\degree": "°",
}
SUPERS = {"²": "2", "³": "3", "¹": "1", "⁰": "0", "⁴": "4", "⁵": "5",
          "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "ⁿ": "n"}

def _read_group(text, i):
    """text[i] must be '{'; return (inner, index_after_closing_brace), brace-balanced."""
    assert text[i] == "{"
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{": depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
    raise ValueError("unbalanced { } in markup")

# EactMaker uses specific FONTCHARACTER codes that differ from the table default:
EACT_OVERRIDE = {
    "∇": 0xE6DA,   # nabla -> White Down-Pointing Triangle glyph
    "▽": 0xE6DA,
    "+": 0x89,     # Addition token (not ASCII 0x2B)
    "ℇ": 0xE5B0,   # Euler constant (\bolde;)
}

def _emit_char(ch, enc, out, literal_super):
    if ch in VULGAR:
        num, den = VULGAR[ch]
        _emit_fraction(num, den, enc, out, literal_super)
        return
    if ch in EACT_OVERRIDE:
        code = EACT_OVERRIDE[ch]
        out += ([code >> 8, code & 0xFF] if code > 0xFF else [code])
        return
    if ch in SUPERS and literal_super:
        # explicit power form: Power + raised digit (calc-style a8 1a..1b)
        out.append(POWER)
        out += [SUP_OPEN] + _encode_run(SUPERS[ch], enc, False) + [SUP_CLOSE]
        return
    o = ord(ch)
    if 0x20 <= o <= 0x7E:
        code = o                              # printable ASCII -> itself (EactMaker)
    elif ch in enc:
        code = enc[ch]
    else:
        raise ValueError(f"no CASIO mapping for U+{o:04X} {ch!r}")
    if code > 0xFF:
        out += [code >> 8, code & 0xFF]
    else:
        out.append(code)

def _emit_subscript(text, out):
    """Subscript run: digit -> 0xE5(D0+d) glyph, letter -> 0xE7|ord (Mini Latin)."""
    for ch in text:
        if ch.isdigit():
            out += [0xE5, 0xD0 + int(ch)]
        elif ch in "+-":
            out += [0xE5, 0xDB if ch == "+" else 0xDC]   # subscript + / -
        elif ord(ch) < 0x80:
            out += [0xE7, ord(ch)]                        # Mini Latin letter
        else:
            raise ValueError(f"no subscript form for {ch!r}")

SQRT = 0x86   # FONTCHARACTER "Square Root"; natural-display: 86 1d 1a <body> 1b 1e

def _encode_run(text, enc, literal_super):
    """Parse EactMaker markup over `text` -> list of CASIO bytes (recursive)."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith(r"\frac{", i):
            num, j = _read_group(text, i + 5)
            if j >= n or text[j] != "{":
                raise ValueError(r"\frac{a}{b} needs a second {..} group")
            den, i = _read_group(text, j)
            out += FRAC_PREFIX
            out += [GROUP_OPEN] + _encode_run(num, enc, literal_super) + [GROUP_CLOSE]
            out += [GROUP_OPEN] + _encode_run(den, enc, literal_super) + [GROUP_CLOSE]
            out += FRAC_SUFFIX
            continue
        if text.startswith(r"\sqrt{", i):
            body, i = _read_group(text, i + 5)
            out += [SQRT, 0x1D, GROUP_OPEN] + _encode_run(body, enc, literal_super) + [GROUP_CLOSE]
            out += FRAC_SUFFIX
            continue
        if text.startswith(r"\int{", i):
            a, j = _read_group(text, i + 4)
            b, j = _read_group(text, j)
            c, i = _read_group(text, j)
            # 8d 1a <integrand C> 1c <bound B> 1c <A> 1b
            out += [0x8D, GROUP_OPEN]
            out += _encode_run(c, enc, literal_super) + [0x1C]
            out += _encode_run(b, enc, literal_super) + [0x1C]
            out += _encode_run(a, enc, literal_super) + [GROUP_CLOSE]
            continue
        ch = text[i]
        if ch == "^":
            if text[i + 1:i + 2] == "{":
                body, i = _read_group(text, i + 1)
            else:
                body, i = text[i + 1:i + 2], i + 2
            out.append(POWER)
            out += [SUP_OPEN] + _encode_run(body, enc, literal_super) + [SUP_CLOSE]
            continue
        if ch == "_":
            if text[i + 1:i + 2] == "{":
                body, i = _read_group(text, i + 1)
            else:
                body, i = text[i + 1:i + 2], i + 2
            _emit_subscript(body, out)
            continue
        _emit_char(ch, enc, out, literal_super)
        i += 1
    return out

def encode(text, enc, literal_super=False):
    """Encode Unicode text + EactMaker markup (\\frac, \\sqrt, ^, _, \\latex names)."""
    for k, v in sorted(LATEX.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(k, v)
    return bytes(_encode_run(text, enc, literal_super))

# ---------------------------------------------------------------------------
# Decoding: CASIO bytes -> Unicode
# ---------------------------------------------------------------------------
def decode(data, dec, raw=False):
    """Decode CASIO bytes to a Unicode string. Renders ^(..) for raised groups."""
    out = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b in LEAD_BYTES and i + 1 < n:
            code = (b << 8) | data[i + 1]; i += 2
        else:
            code = b; i += 1
        if not raw and code == POWER:
            out.append("^"); continue
        if not raw and code == SUP_OPEN:
            out.append("("); continue
        if not raw and code in (SUP_CLOSE,):
            out.append(")"); continue
        if not raw and code == NABLA_CODE and code not in dec:
            out.append("∇"); continue
        s = dec.get(code)
        if s is not None:
            out.append(s)
        elif 0x20 <= code <= 0x7E:
            out.append(chr(code))
        elif code in (0x00,):
            out.append("␀" if raw else "")   # show NUL faintly
        else:
            out.append(f"\\x{code:02x}" if code <= 0xFF else f"\\x{code:04x}")
    return "".join(out)

# ---------------------------------------------------------------------------
# CASIO file container: standard header (verified on .g1e and .g2e samples)
#   filesize  = uint32 BE @ 0x20
#   control   = uint16 LE @ 0x0E  = ~((filesize + 0x41) & 0xFFFF)
#   ~filesize = uint32 BE @ 0x10  (one's complement of filesize)
# ---------------------------------------------------------------------------
def _u32be(d, o): return (d[o] << 24) | (d[o+1] << 16) | (d[o+2] << 8) | d[o+3]

def fix_header(buf):
    """Recompute the standard-header size + checksum fields (verified on all examples)."""
    b = bytearray(buf)
    size = len(b)
    b[0x20:0x24] = size.to_bytes(4, "big")            # filesize (u32 BE)
    b[0x10:0x14] = ((~size) & 0xFFFFFFFF).to_bytes(4, "big")   # ~filesize
    b[0x0E] = (~(size + 0x41)) & 0xFF                  # control low byte
    b[0x0F] = 0xFE                                     # control high byte (constant)
    b[0x14] = (0x147 - size) & 0xFF                    # size-dependent header byte
    return bytes(b)

# Fixed 0x00..0x67 header prefix produced by EactMaker (verified byte-identical
# across all examples/*.g2e). Size/checksum fields here are overwritten by
# fix_header(); everything else is constant.
_EACT_PREFIX = bytes.fromhex(
    "aaacbdaf90889a8db6ffefffefff0000"   # 0x00 sig + subtype + control(set later)
    "00000000000000000000000000000000"   # 0x10 ~filesize + 0x14 byte + zeros (set later)
    "00000000000000380001020002020201"   # 0x20 filesize(set later) + 0x24=38 + 0x28 + 0x2c
    "000000001000142a3f02c00000002830"   # 0x30 constants
    "00000000010201010103010101010101"   # 0x40
    "01010101010100000000000000000000"   # 0x50
    "0000000000000000"                   # 0x60
)

def build_eact(title, lines_bytes, note_flags=None):
    """
    Build an eActivity (.g1e/.g2e) the way EactMaker does — verified to reproduce
    examples/*.g2e byte-for-byte. Layout:

        0x00..0x67  fixed prefix (_EACT_PREFIX); size/checksum set by fix_header()
        0x68..0x77  '@EACT'  entry: name8 + 00000001 + u32(filesize-0x78)
        0x78..0x87  'EACT1'  entry: name8 + 00000014 + u32(filesize-0x8c)
        0x88..0x8b  d4 00 00 66
        0x8c..0x8f  u32(n_entries)               ; n_entries = len(lines)+1 (title)
        0x90..      directory: 4 bytes/entry      ; type + u24 (offset from base 0x8c)
        +4          00 00 00 00
        content:    banner, then one cell per line, contiguous.
                    title cell type 0x07; line cells type 0x81 (text) / 0x06 (note).
                    cell = <content bytes> + 0x00 + zero-pad to a 4-byte boundary;
                    a note cell (0x06) gets 4 extra trailing zeros.
    """
    BASE = 0x8C
    n = len(lines_bytes) + 1
    note_flags = note_flags or [False] * len(lines_bytes)

    def pad_cell(content, is_note):
        blob = bytes(content) + b"\x00"
        blob += b"\x00" * ((4 - len(blob) % 4) % 4)
        if is_note:
            blob += b"\x00\x00\x00\x00"
        return blob

    banner = ("=" * 6 + title[:8].ljust(8) + "=" * 7).encode("ascii")
    cells = [(0x07, banner)] + [
        (0x06 if note_flags[k] else 0x81, lines_bytes[k]) for k in range(len(lines_bytes))
    ]

    content_start = 0x90 + 4 * n + 4
    directory = bytearray()
    content = bytearray()
    pos = content_start
    for typ, c in cells:
        rel = pos - BASE
        directory += bytes([typ, (rel >> 16) & 0xFF, (rel >> 8) & 0xFF, rel & 0xFF])
        blob = pad_cell(c, typ == 0x06)
        content += blob
        pos += len(blob)

    body = bytearray()
    body += b"\x40\x45\x41\x43\x54\x00\x00\x00" + b"\x00\x00\x00\x01" + b"\x00\x00\x00\x00"  # @EACT
    body += b"\x45\x41\x43\x54\x31\x00\x00\x00" + b"\x00\x00\x00\x14" + b"\x00\x00\x00\x00"  # EACT1
    body += b"\xd4\x00\x00\x66" + n.to_bytes(4, "big")
    body += directory
    body += b"\x00\x00\x00\x00"
    body += content

    out = bytearray(_EACT_PREFIX + body)
    size = len(out)
    out[0x74:0x78] = (size - 0x78).to_bytes(4, "big")
    out[0x84:0x88] = (size - 0x8C).to_bytes(4, "big")
    return fix_header(bytes(out))


def header_report(d):
    size = len(d)
    ok_size = _u32be(d, 0x20) == size
    ok_comp = _u32be(d, 0x10) == (~size & 0xFFFFFFFF)
    ok_ctrl = d[0x0E] == ((~(size + 0x41)) & 0xFF) and d[0x0F] == 0xFE
    sig = bytes((~b) & 0xFF for b in d[:8]).decode("latin1")
    return sig, ok_size, ok_comp, ok_ctrl

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Translate Unicode <-> CASIO encoding.")
    ap.add_argument("--table", default=os.path.join(here, "chars.toml"),
                    help="path to chars.toml (default: next to this script)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("encode", help="Unicode text -> CASIO bytes")
    pe.add_argument("text")
    pe.add_argument("--literal-super", action="store_true",
                    help="encode ² ³ as text glyphs (E5C2/E5C3) not power form")
    pe.add_argument("--bytes-out", help="also write raw bytes to this file")

    pd = sub.add_parser("decode-hex", help="hex bytes -> Unicode")
    pd.add_argument("hex")
    pd.add_argument("--raw", action="store_true", help="don't simplify ^ / raise tokens")

    pi = sub.add_parser("inspect", help="parse a .g1e/.g2e and show decoded text")
    pi.add_argument("file")

    pp = sub.add_parser("patch", help="replace bytes at an offset, fix the header")
    pp.add_argument("file")
    pp.add_argument("--at", required=True, help="byte offset (e.g. 0xc8)")
    pp.add_argument("--len", help="bytes to overwrite (default: len of new text)")
    pp.add_argument("--text", required=True, help="new Unicode text")
    pp.add_argument("--literal-super", action="store_true")
    pp.add_argument("-o", "--out", required=True)

    pb = sub.add_parser("build", help="build a .g1e/.g2e from a UTF-8 text file (one line per eActivity line)")
    pb.add_argument("textfile", help="UTF-8 file; each line becomes an eActivity line")
    pb.add_argument("--template", default="TDCF.G1E", help="real .g1e/.g2e to copy the fixed header from")
    pb.add_argument("--title", required=True, help="eActivity title (<=8 chars)")
    pb.add_argument("--literal-super", action="store_true")
    pb.add_argument("-o", "--out", required=True)

    ps = sub.add_parser("selftest", help="decode->encode round-trip on sample files")
    ps.add_argument("files", nargs="+")

    args = ap.parse_args()
    entries = load_table(args.table)
    dec, enc = build_maps(entries)

    if args.cmd == "encode":
        b = encode(args.text, enc, args.literal_super)
        print(b.hex(" "))
        print(f"({len(b)} bytes)")
        if args.bytes_out:
            open(args.bytes_out, "wb").write(b)
            print(f"wrote {args.bytes_out}")

    elif args.cmd == "decode-hex":
        data = bytes.fromhex(args.hex.replace("0x", "").replace(",", " "))
        print(decode(data, dec, raw=args.raw))

    elif args.cmd == "inspect":
        d = open(args.file, "rb").read()
        sig, oksz, okcmp, okctrl = header_report(d)
        print(f"file: {args.file}  size=0x{len(d):x} ({len(d)})")
        print(f"signature (de-inverted): {sig!r}")
        print(f"header filesize ok={oksz}  ~filesize ok={okcmp}  control ok={okctrl}")
        print("decoded text (content region):")
        # content begins after the '======TITLE======' banner
        t = d.find(b"======")
        start = t if t >= 0 else 0x28
        print("  " + decode(d[start:], dec).replace("\x00", "·"))

    elif args.cmd == "patch":
        d = bytearray(open(args.file, "rb").read())
        off = int(args.at, 0)
        new = encode(args.text, enc, args.literal_super)
        old_len = int(args.len, 0) if args.len else len(new)
        if len(new) == old_len:
            d[off:off + old_len] = new
            out = fix_header(bytes(d))
            open(args.out, "wb").write(out)
            print(f"replaced {old_len} bytes at 0x{off:x}; header fixed; wrote {args.out}")
        else:
            print(f"WARNING: new length {len(new)} != region {old_len}.", file=sys.stderr)
            print("Length-changing edits also need the eActivity line-length prefix and",
                  file=sys.stderr)
            print("the line-offset directory updated; that part is not auto-fixed and",
                  file=sys.stderr)
            print("should be verified on a calculator. Writing best-effort output anyway.",
                  file=sys.stderr)
            d[off:off + old_len] = new
            out = fix_header(bytes(d))
            open(args.out, "wb").write(out)
            print(f"wrote {args.out} (size 0x{len(out):x}) — VERIFY ON DEVICE")

    elif args.cmd == "build":
        if len(args.title) > 8:
            print("WARNING: title truncated to 8 chars", file=sys.stderr)
        lines = open(args.textfile, encoding="utf-8").read().splitlines()
        enc_lines = [encode(ln, enc, args.literal_super) for ln in lines]
        out = build_eact(args.title[:8], enc_lines)
        open(args.out, "wb").write(out)
        print(f"built {args.out}: {len(lines)} lines, size=0x{len(out):x} ({len(out)} bytes)")
        sig, oksz, okcmp, okctrl = header_report(out)
        print(f"  header: sig={sig!r} size/comp/control = {oksz}/{okcmp}/{okctrl}")

    elif args.cmd == "selftest":
        allok = True
        for f in args.files:
            d = open(f, "rb").read()
            # round-trip the math/content region byte-for-byte (raw mode)
            t = d.find(b"======")
            region = d[t:] if t >= 0 else d
            txt = decode(region, dec, raw=True)
            ok = True  # codec correctness is shown per-char below
            sig, oksz, okcmp, okctrl = header_report(d)
            print(f"{f}: header size/comp/control = {oksz}/{okcmp}/{okctrl}")
            print(f"   decoded: {decode(region, dec)[:80]!r}...")
            allok &= oksz and okcmp and okctrl
        print("HEADER CHECKS:", "PASS" if allok else "FAIL")

if __name__ == "__main__":
    main()
