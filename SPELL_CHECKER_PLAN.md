# Greek Spell Checker — Design & Implementation Plan

A handoff document capturing the design decisions and implementation plan for a Greek language spell checker. Prototype in Python, production implementation in Rust.

---

## 1. Architecture Overview

A traditional spell checker is a five-stage pipeline:

```
lexicon → normalize/tokenize input → detect non-words → generate candidates → score → return ranked suggestions
```

- **Lexicon**: the authoritative set of valid words (possibly generated from stems + morphology rules rather than stored as a flat list).
- **Normalize/tokenize**: Unicode normalization and splitting input text into word tokens.
- **Detect non-words**: for each token, check membership in the lexicon.
- **Generate candidates**: for non-words, find dictionary entries within small edit distance.
- **Score & rank**: order candidates by edit distance, frequency, phonetic similarity, and (optionally) context.

Typical output is a ranked list of 3–5 suggestions, not a single auto-correction.

---

## 2. Greek-Specific Concerns

Greek is morphologically rich and has Unicode subtleties that must be handled up front.

### Unicode
- **Normalize everything to NFC** before lexicon lookup. Greek accented characters have both precomposed and decomposed forms (e.g., ά = U+03AC or U+03B1 + U+0301).
- **Final sigma (ς vs σ)**: same letter, positional variant. Handle in the lexicon or normalize internally.
- **Case folding**: Greek uppercase drops accents (Άθήνα → ΑΘΗΝΑ). Be careful with case-insensitive matching.
- **Polytonic vs monotonic**: decide on a target. Modern text is monotonic (acute only); classical and some literary text is polytonic. Start with monotonic.

### Morphology
- Heavy inflection: nouns/adjectives inflect for gender, number, case; verbs have hundreds of forms per lemma.
- Either store all inflected forms (large but simple) or use stems + affix rules (compact, principled). Hunspell `el_GR` already does the latter.

### Common Error Classes
- **Homophone confusions** (ι/η/υ/ει/οι → /i/, ο/ω → /o/, ε/αι → /e/). These are far more common than random typos and should have low edit costs.
- **Accent errors** (missing/misplaced tonos) — decide whether to treat as errors or softly flag.
- **Final sigma mistakes** at word boundaries.
- Standard typos: keyboard adjacency, transposition, insertion, deletion.

---

## 3. Lexicon Sourcing

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

## 4. Phase 1 — Python Prototype

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

### First-week tasks
The index.dic and index.aff files are the root of this repo. Book as corpus examples from Project Gutenberg are under books/
1. Parse the `.dic` file (simpler) and get a flat word list going. Revisit `.aff` expansion later.
2. Build the minimal pipeline end-to-end.
3. Assemble the 50–100 item test set and measure baseline accuracy.

---

## 5. Phase 2 — Rust Implementation

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

## 6. Optional Future Extensions

Not part of the initial plan, but possible follow-ups:

- **Context-sensitive correction**: n-gram language model over a Greek corpus to catch real-word errors (e.g., κλίμα vs κλήμα). J&M Chapter 3 covers this.
- **Morphology-aware lexicon**: full expansion of Hunspell `.aff` rules, or a hand-written finite-state morphology (see Beesley & Karttunen, *Finite State Morphology*).
- **Phonetic-key lookup**: Greek-adapted Soundex/Metaphone for the ι/η/υ confusion class.
- **Neural ranking**: small transformer scoring candidates in context. Rust via `candle` or ONNX runtime if you want to stay in-ecosystem.
- **Deployment targets**: CLI tool, library crate, WASM for browser use, LSP server for editor integration.

---

## 7. Reading List

### From Jurafsky & Martin, *Speech and Language Processing*, 3rd ed. (Jan 2026 draft)
- **Chapter 2** (Words and Tokens) — read end-to-end. Covers Unicode (§2.3), regex (§2.6), tokenization (§2.7–2.8), edit distance (§2.9).
- **Chapter 3** (N-gram Language Models) — when you're ready to add frequency ranking or context-sensitive correction.

### Missing from the 3rd edition, get elsewhere
- **Morphology and finite-state transducers**: pull up the 2nd edition of J&M (Chapter 3, "Words and Transducers"). The 3rd edition dropped this material.
- **Finite-state morphology in depth**: Beesley & Karttunen, *Finite State Morphology* (2003), freely available online. Essential if writing morphology from scratch.
- **Classic short intro to spelling correction**: Peter Norvig, "How to Write a Spelling Corrector" — the 20-line Python approach that's still the best starting point.
- **Hunspell `.aff`/`.dic` format docs** — read these directly; they're what you actually need for Phase 1 parsing.

---

## 8. Open Questions to Resolve

Things deliberately left unresolved; pick answers during Phase 1:

- [ ] Monotonic only, or polytonic support?
- [ ] Weighted edits for ι/η/υ class, or phonetic-key preprocessing?
- [ ] Handle `.aff` affix expansion in Phase 1, or punt to Phase 2?
- [ ] Proper nouns: ignore, flag, or maintain a separate name list?
- [ ] Treat missing accents as errors or soft warnings?
- [ ] Target accuracy threshold before moving to Phase 2 (e.g., 85% top-5)?
