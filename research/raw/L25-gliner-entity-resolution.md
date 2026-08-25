# L25 — T4 entity-res: GLiNER zero-shot NER (local CPU)

(recovered from lane yield; verdict: strong adopt — gliner2.5-base 194M Apache-2.0 primary, gliner_medium-v2.1 fallback, gline-rs ONNX if floor tightens)

## GLiNER zero-shot NER benchmark results

There is **no single original GLiNER benchmark table covering NuNER, Pile-NER, CrossNER, and Few-NERD**. These datasets/models play different roles:

| Item | Role | Reported GLiNER result |
|---|---|---:|
| **Pile-NER** | Synthetic pretraining corpus used to train GLiNER | Not a held-out zero-shot benchmark in the original paper |
| **CrossNER + MIT Movie/Restaurant** | Original out-of-domain zero-shot benchmark | **60.9 average F1** for GLiNER-L |
| **CrossNER only** | Five CrossNER domains, excluding MIT datasets | **65.3 average F1** for GLiNER-L |
| **Few-NERD** | Later general-domain zero-shot evaluation | **47.22 F1** for GLiNER2 Base; **51.49 F1** for GLiNER2 Multilingual |
| **NuNER / NuNER-Zero** | Alternative pretrained NER models, not merely an evaluation dataset | **40.87 macro-mean F1** for NuNER-Zero in a later biomedical evaluation |

### Original GLiNER paper: GLiNER-L

The original GLiNER paper evaluated zero-shot performance on five CrossNER domains plus MIT Movie and MIT Restaurant:

| Dataset | GLiNER-L F1 |
|---|---:|
| MIT Movie | 57.2 |
| MIT Restaurant | 42.9 |
| CrossNER-AI | 57.2 |
| CrossNER-Literature | 64.4 |
| CrossNER-Music | 69.6 |
| CrossNER-Politics | 72.6 |
| CrossNER-Science | 62.6 |
| **Average, all seven datasets** | **60.9** |

The paper’s reported **60.9** is therefore the average over **7 datasets**, not CrossNER’s five domains alone. Averaging only the five CrossNER domains gives approximately **65.3 F1**. ([cs.jhu.edu](https://www.cs.jhu.edu/~kevinduh/t/naacl24/final_pdf/paper580.pdf?utm_source=openai))

### Few-NERD results

A later official GLiNER2.5 comparison reports zero-shot results on Few-NERD:

| Model | Few-NERD F1 |
|---|---:|
| GLiNER2 Base | 47.22 |
| GLiNER2 Multilingual | 51.49 |
| GLiNER2.5 Base | **55.14** |
| GLiNER2.5 Multilingual | 52.37 |

These are reported as F1 values on the general NER benchmark based on Few-NERD. The benchmark uses the broad Few-NERD entity-extraction setup rather than the original supervised or episodic few-shot protocols. ([fastino.ai](https://fastino.ai/models/gliner2-5?utm_source=openai))

### NuNER and NuNER-Zero

NuNER is better understood as a **pretraining/model family**, while **NuNER-Zero** is a zero-shot model that can be compared with GLiNER. In a later evaluation aggregated over eight biomedical datasets, the reported macro-mean F1 scores were:

| Model | Micro F1 | Macro mean F1 | Macro median F1 |
|---|---:|---:|---:|
| NuNER-Zero | 40.87 | 21.79 | 13.94 |
| NuNER-Zero-span | 40.26 | 22.51 | 14.27 |
| GLiNER v1.0 | 47.77 | 29.60 | 21.13 |
| GLiNER v2.1 | 48.04 | 29.75 | 28.20 |
| GLiNER v2.5 | 53.81 | 35.22 | 35.65 |

These numbers are **biomedical aggregate results**, so they should not be directly compared with the original CrossNER average without accounting for the different datasets, label sets, and averaging procedures. ([academic.oup.com](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923?utm_source=openai))

## Bottom line

For the commonly cited original GLiNER result:

> **GLiNER-L: 60.9 average zero-shot F1 on the seven-dataset CrossNER/MIT out-of-domain benchmark.**

More precisely:

- **65.3 F1** on the five CrossNER domains alone
- **60.9 F1** when MIT Movie and MIT Restaurant are included
- **47.22 F1** for GLiNER2 Base on Few-NERD
- **55.14 F1** for GLiNER2.5 Base on Few-NERD
- **Pile-NER** is primarily GLiNER’s pretraining data, not the original evaluation benchmark
- **NuNER-Zero** is a competing zero-shot NER model, with later biomedical aggregate results rather than an original GLiNER benchmark score

## Sources
47 sources
[1] https://huggingface.co/knowledgator/gliner-bi-large-v2.0/blame/main/README.md
    https://huggingface.co/knowledgator/gliner-bi-large-v2.0/blame/main/README.md
[2] GLiNER-BioMed: a suite of efficient models for open biomedical named entity recognition | Bioinformatics | Oxford Academic
    https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923
    ossNER average without accounting for the different datasets, label sets, and averaging procedures. (academic.oup.com)

## Bottom line

For the commonly cited original GLiNER result:

> **GLiNER-L: 60.9 average zero-sh
[3] GLiNER: Generalist Model for Named Entity Recognition using
    https://www.cs.jhu.edu/~kevinduh/t/naacl24/final_pdf/paper580.pdf
    NER’s five domains alone. Averaging only the five CrossNER domains gives approximately **65.3 F1**. (cs.jhu.edu)

### Few-NERD results

A later official GLiNER2.5 comparison reports zero-shot results on Few-NERD:
[4] https://github.com/urchade/GLiNER/blob/main/docs/intro.md
    https://github.com/urchade/GLiNER/blob/main/docs/intro.md
[5] https://www.researchgate.net/publication/382634629_GLiNER_Generalist_Model_for_Named_Entity_Recognition_using_Bidirectional_Transformer
    https://www.researchgate.net/publication/382634629_GLiNER_Generalist_Model_for_Named_Entity_Recognition_using_Bidirectional_Transformer
[6] https://slavadubrov.github.io/es/blog/2026/04/02/ner-guide/
    https://slavadubrov.github.io/es/blog/2026/04/02/ner-guide/
[7] https://fastino.ai/blog/gliner2-5-span-free-information-extraction
    https://fastino.ai/blog/gliner2-5-span-free-information-extraction
[8] https://socket.dev/huggingface/package/knowledgator/gliner-multitask-large-v0.5?type=model
    https://socket.dev/huggingface/package/knowledgator/gliner-multitask-large-v0.5?type=model
[9] https://slavadubrov.github.io/nl/blog/2026/04/02/ner-guide/
    https://slavadubrov.github.io/nl/blog/2026/04/02/ner-guide/
[10] https://huggingface.co/jilijeanlouis/NuNER_Zero
    https://huggingface.co/jilijeanlouis/NuNER_Zero
[11] https://arxiv.org/abs/2602.18487
    https://arxiv.org/abs/2602.18487
[12] https://dwb2023-gliner-testbed.hf.space/?__theme=system
    https://dwb2023-gliner-testbed.hf.space/?__theme=system
[13] https://opencodepapers-b7572d.gitlab.io/benchmarks/few-shot-ner-on-few-nerd-intra.html
    https://opencodepapers-b7572d.gitlab.io/benchmarks/few-shot-ner-on-few-nerd-intra.html
[14] https://arxiv.org/abs/2311.08526
    https://arxiv.org/abs/2311.08526
[15] https://github.com/urchade/gliner?ref=www.awesomepython.org
    https://github.com/urchade/gliner?ref=www.awesomepython.org
[16] https://ojs.aaai.org/index.php/AAAI/article/download/40375/44336
    https://ojs.aaai.org/index.php/AAAI/article/download/40375/44336
[17] https://witness.ai/wp-content/uploads/2026/04/WitnessAI-ML-JPT-NER-paper.pdf
    https://witness.ai/wp-content/uploads/2026/04/WitnessAI-ML-JPT-NER-paper.pdf
[18] https://arxiv.org/abs/2504.00676
    https://arxiv.org/abs/2504.00676
[19] https://www.reddit.com/r/LocalLLaMA/comments/1p69bea/gliner2_unified_schemabased_information_extraction/
    https://www.reddit.com/r/LocalLLaMA/comments/1p69bea/gliner2_unified_schemabased_information_extraction/
[20] https://arxiv.org/abs/2105.07464
    https://arxiv.org/abs/2105.07464
[21] https://www.reddit.com/r/LanguageTechnology/comments/1vfpazu/training_a_multilingual_ner_relationextraction/
    https://www.reddit.com/r/LanguageTechnology/comments/1vfpazu/training_a_multilingual_ner_relationextraction/
[22] https://www.reddit.com/r/u_stephen-leo/comments/1dbsppt
    https://www.reddit.com/r/u_stephen-leo/comments/1dbsppt
[23] https://www.reddit.com/r/u_stephen-leo/comments/1d1pnde
    https://www.reddit.com/r/u_stephen-leo/comments/1d1pnde
[24] https://www.reddit.com/r/LanguageTechnology/comments/1p42kj9/gliner2_seemed_to_have_a_quiet_release_and_the/
    https://www.reddit.com/r/LanguageTechnology/comments/1p42kj9/gliner2_seemed_to_have_a_quiet_release_and_the/
[25] https://www.reddit.com/r/LanguageTechnology/comments/1jkbk4y/best_ner_models/
    https://www.reddit.com/r/LanguageTechnology/comments/1jkbk4y/best_ner_models/
[26] https://www.reddit.com/r/MachineLearning/comments/1bbxpsi
    https://www.reddit.com/r/MachineLearning/comments/1bbxpsi
[27] https://www.reddit.com/r/LanguageTechnology/comments/1n34307
    https://www.reddit.com/r/LanguageTechnology/comments/1n34307
[28] https://www.reddit.com/r/MachineLearning/comments/1ao4ayw
    https://www.reddit.com/r/MachineLearning/comments/1ao4ayw
[29] https://www.reddit.com/r/LocalLLaMA/comments/1bvf6s2
    https://www.reddit.com/r/LocalLLaMA/comments/1bvf6s2
[30] https://www.reddit.com/r/learnmachinelearning/comments/19316wi
    https://www.reddit.com/r/learnmachinelearning/comments/19316wi
[31] https://www.reddit.com/r/LocalLLaMA/comments/1jil577
    https://www.reddit.com/r/LocalLLaMA/comments/1jil577
[32] https://www.researchgate.net/publication/403604885_Just_Pass_Twice_Efficient_Token_Classification_with_LLMs_for_Zero-Shot_NER
    https://www.researchgate.net/publication/403604885_Just_Pass_Twice_Efficient_Token_Classification_with_LLMs_for_Zero-Shot_NER
[33] Fastino Labs
    https://fastino.ai/models/gliner2-5
    ew-NERD entity-extraction setup rather than the original supervised or episodic few-shot protocols. (fastino.ai)

### NuNER and NuNER-Zero

NuNER is better understood as a **pretraining/model family**, while **Nu
[34] https://github.com/thunlp/Few-NERD
    https://github.com/thunlp/Few-NERD
[35] https://www.researchgate.net/publication/405179302_GLiNER-BioMed_a_suite_of_efficient_models_for_open_biomedical_named_entity_recognition
    https://www.researchgate.net/publication/405179302_GLiNER-BioMed_a_suite_of_efficient_models_for_open_biomedical_named_entity_recognition
[36] https://aclanthology.org/2024.naacl-long.300.pdf
    https://aclanthology.org/2024.naacl-long.300.pdf
[37] https://github.com/tomaarsen/SpanMarkerNER
    https://github.com/tomaarsen/SpanMarkerNER
[38] https://www.emergentmind.com/topics/gliner2-fd4b490d-971b-4044-9045-d036f5afb1d7
    https://www.emergentmind.com/topics/gliner2-fd4b490d-971b-4044-9045-d036f5afb1d7
[39] https://aclanthology.org/2025.bionlp-1.pdf
    https://aclanthology.org/2025.bionlp-1.pdf
[40] https://github.com/modelscope/AdaSeq/blob/master/docs/datasets.md
    https://github.com/modelscope/AdaSeq/blob/master/docs/datasets.md
[41] https://www.emergentmind.com/topics/gliner-architecture
    https://www.emergentmind.com/topics/gliner-architecture
[42] https://aclanthology.org/2025.bionlp-1.9.pdf
    https://aclanthology.org/2025.bionlp-1.9.pdf
[43] https://www.researchgate.net/publication/390404555_GLiNER-biomed_A_Suite_of_Efficient_Models_for_Open_Biomedical_Named_Entity_Recognition
    https://www.researchgate.net/publication/390404555_GLiNER-biomed_A_Suite_of_Efficient_Models_for_Open_Biomedical_Named_Entity_Recognition
[44] https://www.researchgate.net/publication/387078555_Familiarity_Better_Evaluation_of_Zero-Shot_Named_Entity_Recognition_by_Quantifying_Label_Shifts_in_Synthetic_Training_Data
    https://www.researchgate.net/publication/387078555_Familiarity_Better_Evaluation_of_Zero-Shot_Named_Entity_Recognition_by_Quantifying_Label_Shifts_in_Synthetic_Training_Data
[45] https://www.emergentmind.com/topics/nuner
    https://www.emergentmind.com/topics/nuner
[46] https://www.diva-portal.org/smash/get/diva2%3A1973746/FULLTEXT01.pdf
    https://www.diva-portal.org/smash/get/diva2%3A1973746/FULLTEXT01.pdf
[47] https://access.archive-ouverte.unige.ch/access/metadata/0f13fd4e-02a4-49dc-9c23-a0f0dbed8b8f/download
    https://access.archive-ouverte.unige.ch/access/metadata/0f13fd4e-02a4-49dc-9c23-a0f0dbed8b8f/download