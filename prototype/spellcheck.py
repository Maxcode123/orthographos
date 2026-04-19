"""Greek spell checker — Phase 1 prototype.

Pipeline: NFC-normalize → tokenize → lexicon lookup → Norvig edits → rank by
(edit_distance, -frequency). Lexicon comes from the flat Hunspell el_GR .dic
file at the repo root. Frequencies come from books/ via `build-freq`.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DICT_PATH = ROOT / "index.dic"
BOOKS_DIR = ROOT / "books"
FREQ_PATH = Path(__file__).resolve().parent / "frequencies.tsv"
TEST_PATH = Path(__file__).resolve().parent / "test_cases.tsv"

# Lowercase Greek letters that may appear inside a dictionary word, used as
# the edit alphabet for Norvig-style candidate generation.
GREEK_LETTERS = "αβγδεζηθικλμνξοπρστυφχψωάέήίόύώϊϋΐΰς"

# A Greek word token: one or more Greek letters, optionally with an internal
# apostrophe (σ' αυτό → σ, αυτό) — but we treat the apostrophe as a separator.
GREEK_WORD_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]+")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    if s.endswith("σ"):
        s = s[:-1] + "ς"
    return s


def tokenize(text: str) -> list[tuple[str, int]]:
    text = unicodedata.normalize("NFC", text)
    return [(m.group(0), m.start()) for m in GREEK_WORD_RE.finditer(text)]


def load_lexicon(path: Path = DICT_PATH) -> set[str]:
    words: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            w = line.strip()
            if not w:
                continue
            if i == 0 and w.isdigit():
                continue
            w = w.split("/", 1)[0]
            words.add(normalize(w))
    return words


def build_frequencies(books_dir: Path = BOOKS_DIR) -> Counter[str]:
    counter: Counter[str] = Counter()
    for txt in sorted(books_dir.glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        for tok, _ in tokenize(text):
            counter[normalize(tok)] += 1
    return counter


def save_frequencies(counter: Counter[str], path: Path = FREQ_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for w, c in counter.most_common():
            f.write(f"{w}\t{c}\n")


def load_frequencies(path: Path = FREQ_PATH) -> dict[str, int]:
    freq: dict[str, int] = {}
    if not path.exists():
        return freq
    with open(path, encoding="utf-8") as f:
        for line in f:
            w, c = line.rstrip("\n").split("\t")
            freq[w] = int(c)
    return freq


def edits1(word: str) -> set[str]:
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [L + R[1:] for L, R in splits if R]
    transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
    replaces = [L + c + R[1:] for L, R in splits if R for c in GREEK_LETTERS]
    inserts = [L + c + R for L, R in splits for c in GREEK_LETTERS]
    return set(deletes + transposes + replaces + inserts)


def edits2(word: str) -> set[str]:
    return {e2 for e1 in edits1(word) for e2 in edits1(e1)}


def suggest(
    word: str,
    lexicon: set[str],
    freq: dict[str, int],
    n: int = 5,
) -> list[str]:
    w = normalize(word)
    if w in lexicon:
        return [w]
    e1 = {c for c in edits1(w) if c in lexicon}
    e2 = {c for c in edits2(w) if c in lexicon} - e1
    # Rank by (edit_distance, -frequency). Merging e1 and e2 (rather than
    # Norvig's "prefer e1, fall back to e2") surfaces distance-2 corrections
    # when the user made two errors — e.g. missing-accent + missing-letter.
    ranked_e1 = sorted(e1, key=lambda c: (-freq.get(c, 0), c))
    ranked_e2 = sorted(e2, key=lambda c: (-freq.get(c, 0), c))
    return (ranked_e1 + ranked_e2)[:n]


def check_text(
    text: str,
    lexicon: set[str],
    freq: dict[str, int],
    n: int = 5,
) -> list[tuple[str, int, list[str]]]:
    issues = []
    for tok, offset in tokenize(text):
        if normalize(tok) in lexicon:
            continue
        issues.append((tok, offset, suggest(tok, lexicon, freq, n=n)))
    return issues


def _cmd_suggest(args, lexicon, freq):
    for s in suggest(args.word, lexicon, freq):
        print(s)


def _cmd_check(args, lexicon, freq):
    src = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    for tok, offset, suggestions in check_text(src, lexicon, freq):
        tail = ", ".join(suggestions) if suggestions else "(no suggestions)"
        print(f"[{offset}] {tok} -> {tail}")


def _cmd_evaluate(args, lexicon, freq):
    top1 = top5 = total = 0
    with open(args.cases, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            misspell, expected = line.split("\t")
            expected_n = normalize(expected)
            suggestions = suggest(misspell, lexicon, freq, n=5)
            total += 1
            if suggestions and suggestions[0] == expected_n:
                top1 += 1
            if expected_n in suggestions:
                top5 += 1
            else:
                print(f"MISS  {misspell!r} -> {expected!r}  got: {suggestions}")
    if total:
        print()
        print(f"top-1: {top1}/{total} ({100 * top1 / total:.1f}%)")
        print(f"top-5: {top5}/{total} ({100 * top5 / total:.1f}%)")


def _cmd_build_freq(args, lexicon, freq):
    counter = build_frequencies()
    save_frequencies(counter)
    print(f"wrote {len(counter)} entries to {FREQ_PATH}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_suggest = sub.add_parser("suggest", help="Suggest corrections for a single word")
    p_suggest.add_argument("word")

    p_check = sub.add_parser("check", help="Check a file (or stdin with '-')")
    p_check.add_argument("file", nargs="?", default="-")

    sub.add_parser("build-freq", help="Build frequencies.tsv from books/")

    p_eval = sub.add_parser("evaluate", help="Run the test set and report accuracy")
    p_eval.add_argument("cases", nargs="?", default=str(TEST_PATH))

    args = ap.parse_args(argv)

    if args.cmd == "build-freq":
        _cmd_build_freq(args, None, None)
        return

    lexicon = load_lexicon()
    freq = load_frequencies()
    {
        "suggest": _cmd_suggest,
        "check": _cmd_check,
        "evaluate": _cmd_evaluate,
    }[args.cmd](args, lexicon, freq)


if __name__ == "__main__":
    main()
