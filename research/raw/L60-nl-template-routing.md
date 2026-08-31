# LANE L60 — T9 interfaces: NL→query WITHOUT an LLM

Scope: pattern-matching and classifier-lite routing for natural-language
retrieval questions, with explicit abstention. Evidence was collected
2026-08-25; no later source currentness or target hit rate is claimed.

## Findings table

|Item|Type(tool/repo/strategy/technique)|URL|License|Maturity|StackFit0-5|EffGain0-5|EffectGain0-5|QualGain0-5|AdoptCost0-5(lower=better)|Conf(H/M/L)|KeyEvidence|
|---|---|---|---|---|---|---|---|---|---|---|---|
|Drain3 prompt-template mining over an approved prompt corpus|tool|https://github.com/IBM/Drain3|MIT|v0.9.11, maintained (IBM); streaming + inference-only match mode + custom masking + parameter extraction (PyPI, checked 2026-08-25)|5|3|4|4|1|H|PyPI page verified: masks IPs/NUMs, `<*>` wildcard slots, `match()` mode creates no new clusters — exactly slot-filling template mining for user prompts; ICWS-2017 Drain paper cited therein|
|Aho-Corasick literal-keyword router|tool|https://github.com/WojciechMula/pyahocorasick|BSD-3-Clause (+PD portions)|v2.3.1, active, C ext, py>=3.10, wheels/build fine on py3.13 (PyPI, 2026-08-25)|4|3|3|2|1|H|PyPI verified: single-pass multi-pattern search, pickleable automaton, deterministic runtime independent of needle count|
|FlashText KeywordProcessor|tool|https://github.com/vi3k6i5/flashtext|MIT (LICENSE read 2026-08-25)|Dormant: 5.7k stars, 108 commits, no release activity in years; stable pure-Python, still widely used|4|2|3|2|1|M|GitHub repo inspected 2026-08-25; PyPI page fetch blocked (client challenge) — version pin via lockfile recommended|
|TF-IDF(char-ngram)+LinearSVC intent-classifier-lite|strategy|https://scikit-learn.org|BSD-3-Clause|Mature/stable; interpretable coefficients; package availability not established|4|3|4|3|1|H|Standard scikit-learn pipeline; training and inference cost, dependency fit, and target accuracy require measurement.|
|fastText supervised classifier|tool|https://github.com/facebookresearch/fastText|MIT|Official repo ARCHIVED 2024-03-19; PyPI fasttext 0.9.3 lacks cp313 wheel → use `fasttext-community` (cp313 manylinux wheels as of Apr 2026) or `fasttext-numpy2` 0.10.2 (Nov 2024)|3|3|4|3|2|M|Web verification 2026-08-25 incl. wheel availability per Python version; bag-of-tricks paper arXiv:1607.01759: CPU-second training, linear-model accuracy|
|semantic-router (embedding-similarity routing, NO generative LLM)|tool|https://github.com/aurelio-labs/semantic-router|MIT|v0.1.16, active, 72k wk downloads, py<3.14 (PyPI 2026-08-25); fully-local mode via HuggingFaceEncoder/FastEmbed — no API keys|5|3|4|4|1|H|PyPI README verified: Route(utterances)→SemanticRouter, returns None on no-match (built-in abstention), threshold-optimization notebook, FastEmbed/local encoders documented|
|spaCy Matcher/EntityRuler slot extraction|tool|https://github.com/explosion/spacy|MIT|v3.8.16, very active (7M wk downloads), supports py<3.15 (PyPI 2026-08-25)|3|2|3|4|2|H|Token-pattern rules extract symbol/path/arg slots after a route fires; heavy dep if spaCy not already present|
|Quepy (rule-based NL→SPARQL framework)|tool — precedent only, DO NOT adopt|https://github.com/machinalis/quepy|BSD-3-Clause|Dead: last tag release-0.2 Sep 2013, alpha, py2-era deps (verified 2026-08-25)|1|1|1|1|3|H|Tag date + LICENSE verified; value is architectural inspiration (pattern→query-rule registry), not installation|

**Recorded candidate:** evaluate a literal-keyword tier and an optional local
embedding-similarity tier, each mapping approved examples to bounded query
templates and abstaining on low-confidence input. Drain3 is a possible
offline clustering aid, not evidence that any prompt corpus is authorized or
representative. Query syntax, dependencies, thresholds, and fallback behavior
remain implementation and evaluation decisions.

## Hit-rate expectations (honest assessment)

**Data-hygiene constraint:** Mining requires an explicitly approved corpus,
must exclude machine-generated records, and must minimize retained text. The
principal acceptance criteria are abstention behavior and routing accuracy;
no traffic or recall estimate is retained.

**External calibration:** Affolter, Stockinger & Bernstein, VLDB Journal 28:793–819 (2019), report that keyword and trigger systems handle simpler queries but struggle with nested structure, and caution that evaluation protocols are not directly comparable. Spider 2.0 illustrates the difficulty of enterprise text-to-SQL even for neural systems. The fastText bag-of-tricks study supports CPU-trained linear classifiers, but target precision and coverage require a dedicated labelled evaluation set.

**Closed loop:** measure per-route precision, recall, and abstention on an approved evaluation corpus; review unmatched retrieval-shaped prompts as later template candidates.
