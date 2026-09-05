RECALL_AT_10 = 0.75
MRR = 0.45
NDCG_AT_10 = 0.55
QUALITY_RECALL_AT_10 = 0.90
QUALITY_MRR = 0.70
QUALITY_NDCG_AT_10 = 0.80

# Under LLM_PROVIDER=fake, write_cover_letter/draft_email always produce empty
# strings, so checked=0 claim lines -> ClaimReport.supported_ratio is 1.0 by
# definition, and zero keyword matches -> coverage 0.0. These floors are
# exactly that -- a plumbing check, not a quality gate. QUALITY_* are for a
# future manual run against a real provider.
GROUNDEDNESS_FLOOR = 1.0
KEYWORD_COVERAGE_FLOOR = 0.0
QUALITY_GROUNDEDNESS = 0.85
QUALITY_KEYWORD_COVERAGE = 0.50
