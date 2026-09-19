# L66 — Self-supervised golden-set mining from repository documents and code

Scope: question/evidence pair synthesis from headings, docstrings, and
cross-references, plus quality-control candidates. Public-source claims are
retained as recorded; target precision, throughput, yield, resource use, and
data authority are not established.

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Heading→question template synthesis (h1–h6 tree → "What is X?"/"How do I …?"/"Where is X configured?"; evidence=section text)|technique|https://pmc.ncbi.nlm.nih.gov/articles/PMC9886210/ (AQG survey, 2023)|n/a (candidate code)|high (standard AQG practice)|5|4|3|2|1|H|The cited AQG survey describes template-based question generation; target question quality remains unmeasured.|
|Docstring→query mining via stdlib `ast` (summary-line → query; signature+body → evidence; doctest examples retained)|technique|https://docs.python.org/3/library/ast.html|PSF (stdlib)|high|5|4|3|3|1|H|The standard library exposes syntax trees and docstrings needed to generate candidates. Filtering rules and candidate quality remain design hypotheses.|
|rake-nltk 1.0.6 keyphrase pseudo-queries (statistical, no model)|tool|https://pypi.org/project/rake-nltk/|MIT|high (v1.0.6 stable)|4|3|2|1|0.5|H|PyPI metadata MIT, py>=3.6 (checked 2026-08-25); ~KBs RAM. NOTE: prefer over YAKE — yake 0.7.3 (rel 2026-02-09) is **GPLv3**, license trap|
|KeyBERT 0.9.0 MMR-diverse keyphrase queries with a separately selected embedder|tool|https://pypi.org/project/keybert/|MIT|high (0.9.0 rel 2025-02-07)|4|3|2|2|1|M|PyPI metadata recorded an MIT license. Model compatibility, added memory, and candidate quality require measurement.|
|Cross-encoder pair filtering after labelled calibration|strategy/QC|https://arxiv.org/abs/2010.08191|MIT (recorded model-card license)|high|5|4|5|5|1|H|RocketQA reported a denoising improvement and high manual accuracy at its thresholds. That is a source precedent, not a target precision guarantee; thresholds require a labelled target sample.|
|Syntax/executability gate for code evidence (`ast.parse`/`compile` every code chunk; sandboxed doctest for docstring pairs)|strategy/QC|https://docs.python.org/3/library/doctest.html|PSF|high|5|2|2|2|0.5|H|Guarantees evidence chunks are valid, runnable Python — eliminates silent index-corruption false negatives|
|ranx 0.3.21 (bootstrap CIs, randomization tests) — pick over ir-measures 0.4.3 unless trec_eval parity needed|tool|https://pypi.org/project/ranx/|MIT (ir-measures: Apache-2.0)|high (ranx 0.3.21 rel 2025-08-07; ir-measures 0.4.3 rel 2025-11-25)|4|3|2|3|1|H|Bootstrap CIs on nDCG@10 prevent over-reading small self-supervised sets; ranx also ships RRF fusion utilities matching gated 3-way RRF|
|doc2query-- (T5-small local expansion) as escalation path|technique|https://arxiv.org/abs/2104.07081|Apache-2.0 (models)|mature models|2|4|4|4|4|M|A generative expansion path adds model, resource, and quality risks; the recorded size and timing estimates are hypotheses and require separate model review plus measurement.|

**Recorded candidate:** heading-to-question and docstring-to-query generators
feeding syntax checks, deduplication, labelled cross-encoder calibration, and
bootstrap intervals. Cross-reference generation, retriever-agreement, and
entity-overlap checks remain unverified design hypotheses rather than
public-source findings. All recorded precision, throughput, and yield
expectations are hypotheses; measure them on an authorized labelled sample
before treating output as a golden set.

Evaluation shape: emit candidates from document structure and an `ast` walk,
apply only predeclared quality checks, retain exact source references, and
publish an evaluation report beside the versioned dataset. Data authority,
thresholds, throughput, and retained-pair yield require measurement.
