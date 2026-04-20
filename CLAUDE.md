# Orthographos

Greek spell checker. Phase 1 (Python prototype) is complete. Phase 2 will port to Rust using the `fst` crate for memory-mapped Levenshtein search. See `SPELL_CHECKER_PLAN.md` for the phase roadmap, reading list, and open design questions.

## Architecture

Five-stage pipeline:

```
lexicon → normalize/tokenize input → detect non-words → generate candidates → score → return ranked suggestions
```

- **Lexicon**: authoritative set of valid words. Membership decides "is this a word?"
- **Normalize/tokenize**: NFC + case-fold + Greek-letter regex.
- **Detect non-words**: set lookup.
- **Generate candidates**: Norvig-style edits at distance 1 and 2, filtered through the lexicon.
- **Score & rank**: `(edit_distance, -frequency)`. Merging distance-1 and distance-2 candidates (rather than Norvig's prefer-1-fall-back-to-2) is load-bearing — it's the difference between 78.7% and 91.5% top-5 on the test set.

Output is a ranked list of ≤5 suggestions, not a single auto-correction.

## Layout

- `index.dic`, `index.aff` — Hunspell `el_GR` dictionary. The `.dic` is already fully expanded (828,806 forms); the `.aff` affix rules are kept for reference.
- `books/` — small Greek corpus (Modern Greek translations of Aeschylus and Plato) used only for frequency data. Literary-biased — a known Phase 1 limitation.
- `prototype/` — Phase 1 Python implementation (uv-managed; see `prototype/pyproject.toml`).
  - `spellcheck.py` — pipeline + CLI.
  - `test_cases.tsv` — 47-case regression suite.
  - `frequencies.tsv` — 8,135 word counts; committed so `evaluate` runs without a build step.
  - `pyproject.toml`, `uv.lock`, `.python-version` — uv project metadata. Run `uv sync` inside `prototype/` to materialize the venv.
- `SPELL_CHECKER_PLAN.md` — project-wide roadmap, open questions, reading list.
- `plans/features/` — feature-level plans (one file per track). See § Plans.

## Running

Two equivalent entry points. From the **repo root**, using whatever Python 3.10+ is on PATH:

```
python3 -m prototype.spellcheck suggest WORD
python3 -m prototype.spellcheck check FILE_OR_DASH       # `-` reads stdin
python3 -m prototype.spellcheck build-freq               # regenerate frequencies.tsv from books/
python3 -m prototype.spellcheck evaluate                 # run test_cases.tsv, report top-1 / top-5
```

Or from inside **`prototype/`** via the uv-managed venv (picks up the pinned interpreter in `.python-version`):

```
uv run python -m spellcheck suggest WORD
uv run python -m spellcheck check FILE_OR_DASH
uv run python -m spellcheck build-freq
uv run python -m spellcheck evaluate
```

`evaluate` takes ~7s and reports top-1 and top-5 accuracy.

## Invariants

Greek is morphologically rich and has Unicode subtleties. The prototype encodes the following decisions; keep them coherent if you change the pipeline.

- **NFC-normalize before lexicon lookup.** Accented Greek letters have both precomposed and decomposed forms (ά = U+03AC or U+03B1 + U+0301) which would otherwise mismatch.
- **Lowercase, then rewrite trailing `σ` → `ς`.** Python's `str.lower` doesn't produce final sigma contextually; `normalize()` patches this.
- **The tokenizer matches runs of Greek letters only.** Apostrophes, punctuation, and Latin text act as separators — so `σ' αυτό` yields two tokens, and embedded English is simply skipped.
- **Proper nouns are already in the lexicon** (Άαχεν, Αθήνα, …). Lowercasing during lookup lets them match; no separate name list is needed.
- **Missing accents are currently hard errors.** The unaccented form isn't in the dictionary, so it gets flagged as a non-word and the accented form surfaces as a candidate. Reclassifying as a soft warning is open (plan §6 Q2).
- **Polytonic input isn't supported.** The tokenizer regex covers the polytonic Unicode block, but no test case exercises it. Revisit only when a polytonic corpus becomes a target.

### Common Greek error classes (in rough order of frequency)

- **Homophone confusions**: ι/η/υ/ει/οι → /i/, ο/ω → /o/, ε/αι → /e/. Currently uniform-cost edits — which caps top-1 ≈ 60% on the test set. Weighted edits vs phonetic keying is the active design question in plan §6.
- **Accent errors**: missing tonos, wrong position.
- **Final sigma mistakes** at word boundaries — masked by the `σ → ς` normalization above.
- **Standard typos**: adjacency, transposition, insertion, deletion.

## Baseline

Last measured at commit `58c0ba4`:

- top-1: 57.4%
- top-5: 91.5%
- runtime: ~7s for 47 cases

Update the Results subsection in `SPELL_CHECKER_PLAN.md` when these numbers shift materially.

## Validation

Never declare a change complete without running the test suite against it.

- `python3 -m prototype.spellcheck evaluate` is the correctness oracle: it runs `prototype/test_cases.tsv` end-to-end and reports top-1 / top-5 accuracy.
- If a change touches the pipeline (normalize, tokenize, lexicon load, candidate generation, ranking) or the data it reads (lexicon, frequencies), re-run `evaluate`. Don't assume invariance.
- A drop in top-5 is a regression. A drop in top-1 is either a regression or a deliberate trade — flag which, either way.
- When you fix a behaviour that isn't covered, add a line to `test_cases.tsv` so the next regression is caught.
- There's no CI in this repo; `evaluate` is the closest thing. Type checking and linting aren't wired up, so passing the test suite is the bar.

## Plans

Feature-level plans — new tracks, multi-milestone integrations, subsystem work — live under `plans/features/`, one Markdown file per track. Keeps the repo root uncluttered as work accumulates.

`SPELL_CHECKER_PLAN.md` stays at the root; it's the project-wide roadmap, not a feature plan. Track-specific plans (e.g. `plans/features/POLYTONIC_PLAN.md`) always go in the subdirectory.

When a new track warrants a plan, create it there before starting the work. The plan captures scope, milestones, validation criteria, and open questions so the work doesn't need to re-derive them each session.

## Commits

Every commit should be **atomic** and **self-sufficient**:

- **Atomic**: one logical change per commit. Data files, the design plan, the prototype, and doc updates each get their own commit — not one mega-commit. When a task touches several of these, split the work across commits along those seams.
- **Self-sufficient**: each commit leaves the repo coherent. A reviewer should be able to evaluate the commit in isolation, and checking out any commit should produce a consistent slice of the project. If commit B requires commit A to make sense, A must land first.
- **When to commit**: as soon as a change forms a coherent atomic unit and passes validation (see § Validation), commit it — don't wait for an explicit prompt. A string of small, validated commits is easier to review and revert than one end-of-session blob. Hold off only while a change is mid-refactor or hasn't been validated yet. Pushing is a separate step; keep doing that on request.

Commit messages:

- **Title**: imperative mood, ≤70 characters, no trailing period. Describe what the commit does ("Document Phase 1 results"), not what area it touches ("Plan updates").
- **Body**: explain *why* — the motivation, constraint, or tradeoff that made the change worth making. Mention concrete numbers, incidents, or constraints when they drove the decision. Wrap at ~72 characters.
- Don't restate the diff in prose. The diff is already there; the message exists to carry the context that isn't.

