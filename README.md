# Orthographos

A Greek spell checker. Phase 1 is a working Python prototype; Phase 2 will port it to Rust using the `fst` crate for memory-mapped Levenshtein search.

The prototype is built around the Hunspell `el_GR` dictionary (828,806 fully-expanded Modern Greek word forms) and a small Greek corpus from Project Gutenberg that supplies word frequencies for ranking.

## Status

Phase 1 baseline on the 47-case regression suite (`prototype/test_cases.tsv`):

- **top-1 accuracy**: 57.4% — the correct suggestion is first
- **top-5 accuracy**: 91.5% — the correct suggestion is in the top 5
- runtime: ~7s for all 47 cases (candidate generation is brute-force Python; Phase 2 replaces it)

## Requirements

- Python **3.10** or newer.
- [uv](https://docs.astral.sh/uv/) is optional but recommended — it pins and reproduces the dev environment exactly. Without uv, the stdlib-only prototype runs on any 3.10+ interpreter.

## Setup

```
git clone https://github.com/Maxcode123/orthographos.git
cd orthographos
```

With uv:

```
cd prototype && uv sync
```

That's the whole install — the prototype has no third-party runtime dependencies; `uv sync` just materializes a venv against the pinned 3.10 interpreter.

Without uv, you can skip setup entirely. `python3 -m prototype.spellcheck …` from the repo root works out of the box.

## Usage

Two equivalent entry points.

From the **repo root**, using any Python 3.10+ on PATH:

```
python3 -m prototype.spellcheck suggest WORD
python3 -m prototype.spellcheck check FILE_OR_DASH       # `-` reads stdin
python3 -m prototype.spellcheck build-freq               # rebuild frequencies.tsv from books/
python3 -m prototype.spellcheck evaluate                 # run test_cases.tsv, report top-1 / top-5
```

From inside **`prototype/`** under uv:

```
uv run python -m spellcheck suggest WORD
uv run python -m spellcheck check FILE_OR_DASH
uv run python -m spellcheck build-freq
uv run python -m spellcheck evaluate
```

### Examples

Single-word suggestions:

```
$ python3 -m prototype.spellcheck suggest μηλο
μήλο
μόλο
μύλο
μώλο
μην
```

Checking a short passage from stdin:

```
$ echo "Καλημερα κοσμε, χαιρέτε σας!" | python3 -m prototype.spellcheck check -
[0] Καλημερα -> καλήμερα, καλημέρα, καλύτερα
[9] κοσμε -> άκοσμε, άοσμε, κοσμά, κοσμεί, κοσμώ
[16] χαιρέτε -> χαιρέτα, χαίρατε, χαίρετε, χαιρέας, χαιρέταγε
```

Each flagged token is prefixed with its character offset in the input.

Checking a file:

```
python3 -m prototype.spellcheck check path/to/greek.txt
```

Re-running the regression suite:

```
$ python3 -m prototype.spellcheck evaluate
MISS  'μικρο' -> 'μικρό'  got: ['μικρο']
MISS  'πεδι' -> 'παιδί'  got: [...]
...
top-1: 27/47 (57.4%)
top-5: 43/47 (91.5%)
```

## How it works

Five-stage pipeline:

```
lexicon → normalize/tokenize input → detect non-words → generate candidates → rank
```

- **Lexicon**: a Python `set` of all 828,806 forms from `index.dic`, loaded into memory.
- **Normalize/tokenize**: NFC-normalize, lowercase, rewrite trailing `σ` → `ς`; tokenize with a Greek-letter regex that treats apostrophes and punctuation as separators.
- **Detect non-words**: set membership.
- **Generate candidates**: Norvig-style edits at distance 1 and 2, intersected with the lexicon.
- **Rank**: by `(edit_distance, -frequency)`, with frequencies from `prototype/frequencies.tsv`.

`CLAUDE.md` covers the detailed invariants (Unicode handling, common Greek error classes, the final-sigma rule). `SPELL_CHECKER_PLAN.md` covers the Phase 2 Rust roadmap and the still-open design questions (weighted vs phonetic edits, missing-accent severity, Phase 2 accuracy target).

## Project structure

```
.
├── index.dic              # Hunspell el_GR dictionary (828,806 forms)
├── index.aff              # Hunspell affix rules (kept for reference)
├── books/                 # Modern Greek corpus (Aeschylus, Plato translations)
├── prototype/             # Phase 1 Python implementation
│   ├── spellcheck.py      #   pipeline + CLI
│   ├── test_cases.tsv     #   47-case regression suite
│   ├── frequencies.tsv    #   word counts built from books/
│   ├── pyproject.toml     #   uv project metadata
│   ├── uv.lock
│   └── .python-version
├── CLAUDE.md              # Operational orientation and conventions
└── SPELL_CHECKER_PLAN.md  # Phase roadmap, reading list, open questions
```
