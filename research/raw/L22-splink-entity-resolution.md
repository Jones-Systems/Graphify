# L22 — Splink probabilistic entity resolution

Date recorded: 2026-08-25.

## Recovery status

The committed input mixed draft deliberation with a deterministic four-item comparison and source log. This file retains only that comparison. Dates, versions, download counts, and performance statements below are historical source reports from the recorded access date; they are not current verification or measurements of a target deployment.

## Findings

| Item | Type | URL | License | Maturity | StackFit0-5 | EffGain0-5 | EffectGain0-5 | QualGain0-5 | AdoptCost0-5 (lower=better) | Conf | Key evidence |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Splink 4.0.16 | tool | https://github.com/moj-analytical-services/splink | MIT | stable on recorded date | 5 | 4 | 4 | 4 | 2 | H | The project documentation described embedded DuckDB operation, unsupervised parameter estimation, optional clerical labels, and larger Spark/Athena deployments. A cited census case study reported 58 million records, about 3 billion candidate pairs, and a four-hour global model run. |
| dedupe 3.0.3 | tool | https://github.com/dedupeio/dedupe | MIT | maintained on recorded date | 2 | 2 | 2 | 3 | 3 | M | The recorded package documentation required dataset-specific active-learning labels. |
| recordlinkage 0.16 | tool | https://github.com/J535D165/recordlinkage | BSD-3-Clause | mature; limited scale statement | 2 | 2 | 1 | 2 | 2 | M | Its documentation described use for small or medium-sized files and provided an unsupervised ECM classifier. |
| Zingg 0.7.0 | tool | https://github.com/zinggAI/zingg | AGPL-3.0 | active on recorded date | 0 | 1 | 1 | 3 | 4 | M | The recorded package required Spark and a JVM; its license and operational footprint did not match the stated permissive, embedded target constraints. |

## Verdict

Splink 4.0.x was the leading candidate in the recorded comparison because it combined a permissive license, embedded DuckDB support, and unsupervised estimation. A deployment decision still requires a fresh version check, representative person and organization data, measured memory use, and labelled threshold evaluation. Single-field organization-name matching is outside the fit claimed by the recorded Splink documentation.

## Recorded sources

- Splink package and release records: https://pypi.org/project/splink/ and https://github.com/moj-analytical-services/splink/releases
- Splink training and evaluation documentation: https://moj-analytical-services.github.io/splink/demos/tutorials/04_Estimating_model_parameters.html and https://moj-analytical-services.github.io/splink/demos/tutorials/07_Evaluation.html
- Census case study: https://raw.githubusercontent.com/Data-Linkage/Splink-census-linkage/main/SplinkCaseStudy.pdf
- Splink citation: https://doi.org/10.23889/ijpds.v7i3.1794
- Comparator repositories: https://github.com/dedupeio/dedupe, https://github.com/J535D165/recordlinkage, and https://github.com/zinggAI/zingg
