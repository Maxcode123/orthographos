# Polytonic Greek Support — Integration Plan

Forward plan for adding polytonic Greek spell-checking alongside the current monotonic pipeline. Assumes Phase 1 (monotonic prototype) is complete — see `SPELL_CHECKER_PLAN.md`. This track is scoped to data + pipeline mode switching; it can proceed in parallel with Phase 2's Rust port but is easier to finalize in Python first.

Orientation, invariants, and conventions live in `CLAUDE.md`.

---

## 1. Goal

Accept polytonic Greek input and return polytonic suggestions. End state: a `--polytonic` mode on `spellcheck.py` that swaps the monotonic lexicon + frequency pair for polytonic counterparts, keeping the normalize → tokenize → detect → edits → rank pipeline intact.

### Scope
- Attic + Koine as the mainstream target. Broader dialects only if the source corpora already include them.
- Common polytonic error classes: missing or swapped breathing marks, grave-vs-acute confusions, circumflex errors, missing iota subscript, the standard typos already covered for monotonic.
- Corpus-harvested lexicon of ~500k–1M forms with matching frequency data.

### Out of scope
- Morpheus-driven form generation from lemmas. Principled but 2–3 weeks of work; fall back only if corpus coverage is inadequate.
- Beta-code input from users. Beta-code is for ingesting beta-encoded sources during harvest; internal storage is always Unicode NFC.
- Classical-vs-Byzantine / Katharevousa distinctions.
- Preserving the user's accent style in the output (grave in → grave out). Revisit only if users complain.

---

## 2. Data Sources

**Primary: corpus harvest.** Tokenize a large open polytonic corpus, NFC-normalize, lowercase, deduplicate, filter by minimum occurrence to suppress OCR noise. Derives both the lexicon and the frequencies in one pass.

Candidate sources:

- **First1KGreek** (https://opengreekandlatin.org/) — ~1,500 ancient Greek works in TEI XML, CC-BY-SA, well-cleaned. Main target.
- **Perseus canonical texts** (`perseus-opensource` on GitHub) — overlaps with First1KGreek; use to backfill gaps.
- **Diorisis corpus** — ~10M tokens, already lemmatized and morph-tagged. Cleaner than raw First1KGreek but narrower author coverage.

**Explicitly avoided**: TLG (paywalled), ad-hoc Project Gutenberg scraping (inconsistent encoding, polytonic rendering unreliable).

**Deferred**: Morpheus (via CLTK) for principled lemma → all-forms expansion. Pursue only if harvest coverage is insufficient for the polytonic test set.

Raw corpora live **outside the repo**. A 100MB+ TEI tree has no business in git history; the harvester takes a path argument to a local clone.

---

## 3. Pipeline Changes

The monotonic pipeline must survive intact. Polytonic is additive.

- **Lexicon loading**: `--polytonic` swaps `index.dic` for `polytonic.dic`.
- **Frequencies**: swaps `frequencies.tsv` for `polytonic_freq.tsv`.
- **`normalize()`**: stays NFC + lowercase + final-sigma. Nothing else changes — polytonic characters are already legal Unicode and already lowercased correctly by `str.lower()` in the vast majority of cases (see §7 Risks).
- **Tokenizer**: already matches `U+1F00–U+1FFF`. No change.
- **Edit alphabet (`GREEK_LETTERS`)**: currently a hardcoded 34-character string. Polytonic has ~120 distinct letter+diacritic combinations at lowercase — hardcoding is wrong. **Derive the alphabet at lexicon-load time** from the set of characters actually appearing in the loaded lexicon. This keeps the alphabet tight (only chars that could plausibly appear in a correction) and makes the monotonic and polytonic modes use the same mechanism.

### Consequence: candidate space grows

`edits1` output size scales ~linearly with the alphabet; `edits2` scales ~quadratically. Realistic estimate for polytonic: `edits2` runtime per word grows 2–4× over monotonic. Still workable for Phase 1 evaluation; Phase 2's FST Levenshtein is unaffected.

---

## 4. Integration Shape

CLI:

```
python3 -m prototype.spellcheck --polytonic suggest WORD
python3 -m prototype.spellcheck --polytonic check FILE_OR_DASH
python3 -m prototype.spellcheck --polytonic evaluate
python3 -m prototype.spellcheck harvest-polytonic PATH_TO_FIRST1K   # new subcommand
```

Internal: a `Lexicon` bundle (set + frequency dict + derived alphabet) loaded based on mode. Pipeline functions take the bundle as a parameter instead of reading module globals — this is a small refactor of the current module-level design.

Data files:

- `polytonic.dic` — harvested polytonic forms, one per line, NFC-normalized lowercase. Same format as `index.dic`.
- `polytonic_freq.tsv` — `word<TAB>count`, same format as `frequencies.tsv`.
- `prototype/test_cases_polytonic.tsv` — parallel regression suite.

---

## 5. Milestones

Each milestone is a coherent atomic commit per CLAUDE.md conventions.

1. **Harvester.** Write `harvest-polytonic`: walks TEI XML, extracts text runs, tokenizes, NFC-normalizes, lowercases, counts, filters `freq ≥ 3`, writes `polytonic.dic` + `polytonic_freq.tsv`. Output validated by: top-100 most-frequent tokens are common Greek particles (`καί, δέ, τὸ, ὁ, τοῦ, …`).
2. **Lexicon bundle refactor.** Pull module-level globals out of `spellcheck.py`; pass a `Lexicon` dataclass through the pipeline. Derive `GREEK_LETTERS` from the loaded lexicon. Monotonic baselines must stay at 57.4% / 91.5%.
3. **`--polytonic` flag.** Add CLI flag; route to the polytonic data pair. Smoke-test both modes from the same session.
4. **Polytonic test suite.** Hand-build 30–50 polytonic misspelling → correction pairs. Target coverage: missing breathing (ἀ → a), wrong breathing (ἀ ↔ ἁ), grave/acute confusion, circumflex errors, iota subscript, plain typos, missing-accent cases.
5. **Baseline evaluation.** Run `evaluate --polytonic`. Record top-1 / top-5 and runtime. Compare to monotonic baseline.
6. **Documentation.** Update CLAUDE.md (polytonic invariants, running commands, baselines), README.md (mention polytonic mode with an example), and SPELL_CHECKER_PLAN.md (remove polytonic from open questions; mark as resolved with pointer to this doc).

Estimated effort: 3–5 focused days, dominated by milestones 1 (harvester) and 4 (test set curation).

---

## 6. Validation Criteria

Before declaring polytonic support shipped:

- `evaluate --polytonic` runs end-to-end on the polytonic test set.
- **Top-5 ≥ 85%**. Matching monotonic's 91.5% is a stretch given smaller corpus and larger edit space; 85% is a reasonable floor for a first cut.
- Top-1 reported honestly; no target imposed before measuring.
- Monotonic `evaluate` **unchanged at 57.4% / 91.5%**. Polytonic must not regress monotonic behaviour.
- Runtime per case ≤ 3× monotonic (target ~0.5s average). If `edits2` becomes prohibitive, fall back to edits1-only for polytonic and defer the speedup to Phase 2.

---

## 7. Risks

- **OCR artefacts** survive the freq-≥-3 filter. Scan the bottom quartile of the frequency list before shipping; keep a manual blocklist if needed.
- **Iota subscript vs adscript** inconsistency across sources. Normalize to subscript at harvest time; verify NFC canonicalizes this uniformly across the full corpus.
- **Lowercasing surprises.** Python's `str.lower()` on polytonic is generally lossless, but uppercase polytonic in source texts can lose diacritics if the source used the ΑΘΗΝΑΙ-style accent-stripped uppercasing. Test with a broad sample of the harvest output before trusting.
- **Apostrophes and elision** (κατ' ἐμέ, δι' αὐτοῦ). Current tokenizer splits on apostrophes; verify this is still correct for polytonic — elided forms should probably be their own tokens.
- **Dialect flood.** If First1KGreek is used broadly, Homeric and Doric forms will inflate the lexicon with shapes modern users won't type. Mitigation: filter source authors to Attic/Koine-dominant, or accept broader coverage and note the tradeoff.
- **Lexicon memory footprint.** 2M entries at ~80 bytes each ≈ 160MB in Python `set`. Fine on dev machines; spot-check on target environment before declaring done.
- **Licence attribution.** First1KGreek and Perseus are CC-BY-SA. If the harvested lexicon ships with the repo, include an attribution file or a note in the README pointing at the upstream sources.

---

## 8. Open Questions

- [ ] **Which corpus?** First1KGreek alone, or First1KGreek + Perseus merge? Decide in milestone 1 based on overlap and coverage.
- [ ] **Frequency threshold.** Start at `freq ≥ 3`; adjust after inspecting top and bottom tokens. May need to be higher (5–10) if OCR noise is heavy.
- [ ] **Dialect filtering.** Ship broad first, narrow only if the test set shows false-positive corrections from rare dialects.
- [ ] **`--polytonic` as a persistent flag, or auto-detect from input?** Auto-detect (any `U+1F00–U+1FFF` character in input triggers polytonic mode) is nicer UX but risks mis-routing mixed-script text. Decide after the flag version works.
- [ ] **Merged monotonic+polytonic lexicon.** Would a unified lexicon (all forms of both) let a single mode handle both input styles? Cheaper than mode-switching but risks top-1 degradation from ambiguous corrections. Defer until both modes are working independently.

---

## 9. When to Revisit

- **After milestone 5.** If polytonic top-5 falls short of the 85% floor, choose between (a) expanding the corpus, (b) blocklisting known bad entries in the lexicon, (c) adopting weighted edits or phonetic keying from `SPELL_CHECKER_PLAN.md` §6 Q1 — that lever applies to polytonic too, and arguably harder (breathing-mark confusions are essentially the polytonic analogue of homophone confusions).
- **Before Phase 2's Rust port.** Corpus and lexicon changes are cheap in Python and expensive in Rust. Finalize the data shape and mode-switching contract here before translating.
