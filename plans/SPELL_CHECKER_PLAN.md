# Greek Spell Checker — Roadmap & Open Questions

Forward-looking design plan for a Greek spell checker. Architectural orientation, working invariants, and how to run the prototype live in `CLAUDE.md`; this document covers lexicon sourcing strategy, the Phase 1 → Phase 2 plan, reading list, and the design questions still to resolve.

---

## 1. Lexicon Sourcing

**Primary source: Hunspell `el_GR` dictionary.**
- Files: `el_GR.dic` (stems) + `el_GR.aff` (affix rules encoding morphology).
- Source: LibreOffice dictionaries repo, or the Greek linguistic team's GitHub.
- Represents years of community work encoding Greek inflection. Don't try to beat it from scratch.

**Frequency data: Greek corpus.**
- Options: Greek Wikipedia dump, OSCAR Greek portion, Hellenic National Corpus, Project Gutenberg Greek texts.
- Used for ranking candidates — the lexicon decides "is this a word?", the corpus decides "how common is it?"

**Strategy: hybrid.**
- Hunspell for correctness decisions.
- Corpus frequencies layered on top for ranking.

---

## 2. Phase 1 — Python Prototype

**Goal**: lock in design decisions. Not performance, not production. ~200–400 lines total.

### Scope
1. Load a slice of the Hunspell `el_GR` dictionary (start with 10k–50k words, flat set).
2. Unicode-normalize input (NFC) and tokenize with a regex-based Greek tokenizer.
3. Detect non-words via set membership.
4. Generate candidates using Norvig-style brute force: all edits at distance 1 and 2, filtered through the lexicon.
5. Rank by (edit_distance, -frequency).
6. Return top-5 suggestions per misspelling.

### Deliberately out of scope for Phase 1
- Efficient data structures (no trie, no FSA — just a Python `set`).
- Morphology expansion (use stems or a precomputed flat list; accept missing forms).
- Context-sensitive correction (no n-gram model yet).
- Speed optimization.

### Design questions to answer during prototyping
- How to handle ι/η/υ confusions — as weighted edit operations, or a phonetic-key preprocessing step? Prototype both and measure.
- Polytonic input support, yes or no?
- What does the tokenizer do with: punctuation, final sigma at boundaries, apostrophes (σ' αυτό), numbers, mixed-script words (English embedded in Greek)?
- How to handle proper nouns not in the lexicon — allow, flag, or ignore?
- Treatment of missing accents — error or soft warning?

### Evaluation
- Hand-craft a test set of 50–100 misspellings with expected corrections.
- Measure **top-1 accuracy** (correct suggestion is first) and **top-5 accuracy** (correct suggestion is in the list).
- This test set becomes the regression suite for Phase 2.

### Results

Implemented in `prototype/`:
- `spellcheck.py` — pipeline + CLI (`suggest`, `check`, `build-freq`, `evaluate`). ~170 lines.
- `frequencies.tsv` — 8,135 entries built from the three texts in `books/`.
- `test_cases.tsv` — 47 misspelling→correction pairs (missing accents, homophones, double letters, typos, capitalization).

**Baseline accuracy** (distance-1 and distance-2 candidates merged, ranked by `(edit_distance, -frequency)`):
- top-1: **57.4%**
- top-5: **91.5%**
- runtime: ~7s for 47 cases (dominated by `edits2` brute force in Python)

**Findings:**

1. **Norvig's "edits1-or-fall-back-to-edits2" shortcut is wrong for Greek.** Using it, top-5 was 78.7%; always generating both and ranking by `(distance, -freq)` recovered ~13 points. Because Greek is morphologically rich, most words have many distance-1 neighbors, and genuine corrections often need 2 edits (missing accent + missing letter, e.g. `θαλασα → θάλασσα`, `ελαδα → ελλάδα`). Phase 2's `fst::Levenshtein` returns the full set for free.

2. **Pure (distance, frequency) ranking caps top-1 around 60% on this test set.** `αγαπι → αγάπη` loses to `αγαπά`/`αγαπώ` because the Aeschylus+Plato corpus has more verb forms than noun forms. A bigger corpus helps, but the deeper issue is that ι/η/αι edits should be cheaper than arbitrary substitutions — §6 Q1 (weighted edits vs phonetic key) is now evidence-backed, not speculative.

3. **Real-word errors surface and can't be caught at this layer.** `μικρο` is in the dictionary as an unaccented form, so `μικρο → μικρό` can't be flagged without either an n-gram context check or a soft-accent warning pass. Both are deferred to Phase 2+.

4. **Distance-3 corrections exist in natural typos.** `πεδι → παιδί` needs 3 edits. Rare but visible. Phase 2's Levenshtein automaton makes k=3 affordable if warranted.

---

## 3. Phase 2 — Rust Implementation

**Goal**: make it fast and deployable. Translate, don't redesign.

### Key library mappings

| Python (Phase 1) | Rust (Phase 2) |
|---|---|
| `set` of words | `fst::Set` (memory-mapped, compact, fast) |
| Norvig-style brute-force edits | `fst::automaton::Levenshtein` intersected with the set |
| Python `re` | `regex` crate |
| `unicodedata.normalize` | `unicode-normalization` crate |
| Hand-written edit distance | `strsim` crate |
| Frequency dict | Second FST (word → frequency) or `HashMap` |

### Why the `fst` crate matters
Andrew Gallant's `fst` crate is the single biggest performance lever. It provides:
- Compact finite-state sets/maps with memory-mapped storage.
- Built-in Levenshtein automaton search: `set.search(lev).into_stream()` returns all words within edit distance k. This replaces Phase 1's brute-force candidate generation with something orders of magnitude faster.
- Production-quality; same author as ripgrep.

### Rust skills you'll pick up
- Ownership around `&str` vs `String`.
- `Result`/`?` error handling.
- Cargo, modules, unit tests, benchmarks.
- Reading and using well-designed library APIs.

You will mostly **not** be writing recursive tree structures with mutation, which is where Rust beginners hit the borrow checker wall. The `fst` crate absorbs that complexity.

### Validation
Run the Phase 1 test set against the Rust implementation. Accuracy should match or exceed the Python version; performance should improve by orders of magnitude.

---

## 4. Optional Future Extensions

Not part of the initial plan, but possible follow-ups:

- **Context-sensitive correction**: n-gram language model over a Greek corpus to catch real-word errors (e.g., κλίμα vs κλήμα). J&M Chapter 3 covers this.
- **Morphology-aware lexicon**: full expansion of Hunspell `.aff` rules, or a hand-written finite-state morphology (see Beesley & Karttunen, *Finite State Morphology*).
- **Phonetic-key lookup**: Greek-adapted Soundex/Metaphone for the ι/η/υ confusion class.
- **Neural ranking**: small transformer scoring candidates in context. Rust via `candle` or ONNX runtime if you want to stay in-ecosystem.
- **Deployment targets**: CLI tool, library crate, WASM for browser use, LSP server for editor integration.

---

## 5. Reading List

### From Jurafsky & Martin, *Speech and Language Processing*, 3rd ed. (Jan 2026 draft)
- **Chapter 2** (Words and Tokens) — read end-to-end. Covers Unicode (§2.3), regex (§2.6), tokenization (§2.7–2.8), edit distance (§2.9).
- **Chapter 3** (N-gram Language Models) — when you're ready to add frequency ranking or context-sensitive correction.

### Missing from the 3rd edition, get elsewhere
- **Morphology and finite-state transducers**: pull up the 2nd edition of J&M (Chapter 3, "Words and Transducers"). The 3rd edition dropped this material.
- **Finite-state morphology in depth**: Beesley & Karttunen, *Finite State Morphology* (2003), freely available online. Essential if writing morphology from scratch.
- **Classic short intro to spelling correction**: Peter Norvig, "How to Write a Spelling Corrector" — the 20-line Python approach that's still the best starting point.
- **Hunspell `.aff`/`.dic` format docs** — read these directly; they're what you actually need for Phase 1 parsing.

---

## 6. Open Questions

Phase 1 locked in several decisions (monotonic-only, skip `.aff` expansion, silently accept proper nouns, the NFC+lowercase+`σ→ς` normalization pipeline). Those now live in `CLAUDE.md` as invariants. What remains:

- [ ] **Weighted edits for the ι/η/υ/αι/ει/οι/ο/ω class, or a phonetic-key preprocessing step?** Phase 1 baseline top-1 is 57.4% — a clear signal that uniform edit costs are leaving accuracy on the table. Prototype both in a second Python pass before porting, or do the comparison in Rust where candidate generation is cheap.
- [ ] **Missing accents: hard error or soft warning?** Currently hard: the unaccented form isn't in the dictionary, so it's flagged. Reclassifying would require tagging edits by severity (tonal-only vs letter change).
- [ ] **Target accuracy threshold before moving to Phase 2.** Proposed: top-1 ≥ 75% and top-5 ≥ 95% on the Phase 1 test set, conditional on resolving Q1 above.
