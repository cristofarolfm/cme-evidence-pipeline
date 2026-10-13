# Stress test: the same draft with five planted errors

<!-- Each error mimics a real failure mode of LLM drafting. The verifier should flag all five. -->

## Current evidence

In the dMMR/MSI-H population of RUBY, progression-free survival at 24 months was 61.4% with dostarlimab versus 15.7% with placebo (hazard ratio 0.28) [PMID:36972026].
<!-- ERROR 1: wrong number (HR changed from 0.30 to 0.35) -->
In NRG-GY018, 12-month progression-free survival in the dMMR cohort was 74% with pembrolizumab versus 38% with placebo (hazard ratio 0.35) [PMID:36972022].
<!-- ERROR 2: fabricated citation (PMID that does not exist) -->
A pooled analysis showed that pembrolizumab doubled overall survival in pMMR disease [PMID:99999999].
<!-- ERROR 3: real PMID that points to an unrelated paper (the most convincing kind of hallucination) -->
Lenvatinib plus pembrolizumab is the preferred first-line option for pMMR disease [PMID:39999999].
<!-- ERROR 4: uncited factual claim -->
Immune-related hypothyroidism occurs in about 20% of patients treated with PD-1 inhibitors.
<!-- ERROR 5: citation attached to a claim the source does not discuss -->
Dostarlimab reduces the need for hospital admission due to bowel obstruction compared with chemotherapy [PMID:36399812].
