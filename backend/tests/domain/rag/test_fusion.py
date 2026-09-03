from app.domain.rag.fusion import MMR_LAMBDA, RRF_K, mmr, rrf
from app.domain.rag.types import RetrievalSource, ScoredChunk


def _chunk(ref_id: str, rrf_score: float, embedding: tuple[float, ...] | None) -> ScoredChunk:
    return ScoredChunk(
        ref_id=ref_id, source=RetrievalSource.JOB_CHUNKS, section="description",
        content=ref_id, token_count=10, embedding=embedding,
        vector_rank=None, text_rank=None, rrf_score=rrf_score, mmr_score=None,
    )


def test_rrf_default_k_is_60():
    assert RRF_K == 60


def test_rrf_sums_reciprocal_ranks_across_lists():
    out = rrf(["a", "b", "c"], ["b", "a"])
    assert out["a"] == 1.0 / (60 + 1) + 1.0 / (60 + 2)
    assert out["b"] == 1.0 / (60 + 2) + 1.0 / (60 + 1)
    assert out["c"] == 1.0 / (60 + 3)
    assert out["a"] > out["c"]  # a is high in both lists


def test_rrf_id_absent_from_a_list_contributes_zero_from_it():
    out = rrf(["x"], ["y"])
    assert out["x"] == 1.0 / 61 and out["y"] == 1.0 / 61


def test_rrf_empty_lists_give_empty_dict():
    assert rrf([], []) == {}


def test_mmr_lambda_default():
    assert MMR_LAMBDA == 0.7


def test_mmr_returns_k_items_in_selection_order_and_sets_mmr_score():
    cands = [
        _chunk("a", 1.0, (1.0, 0.0)),
        _chunk("b", 0.9, (0.0, 1.0)),
        _chunk("c", 0.8, (1.0, 0.0)),  # identical vector to "a"
    ]
    out = mmr(cands, k=2)
    assert [c.ref_id for c in out] == ["a", "b"]  # b wins slot 2 over near-duplicate c
    assert all(c.mmr_score is not None for c in out)


def test_mmr_missing_embedding_treated_as_maximally_novel():
    # b has no embedding -> redundancy term is 0, so it beats the near-duplicate
    # "c" for slot 2 even though "c"'s raw relevance is marginally higher.
    cands = [
        _chunk("a", 1.0, (1.0, 0.0)),
        _chunk("b", 0.85, None),
        _chunk("c", 0.9, (1.0, 0.0)),  # identical vector to "a"
    ]
    out = mmr(cands, k=2)
    assert [c.ref_id for c in out] == ["a", "b"]


def test_mmr_k_larger_than_candidates_returns_all():
    cands = [_chunk("a", 1.0, None), _chunk("b", 0.5, None)]
    out = mmr(cands, k=10)
    assert {c.ref_id for c in out} == {"a", "b"}


def test_mmr_all_equal_relevance_normalises_to_one():
    cands = [_chunk("a", 0.4, None), _chunk("b", 0.4, None)]
    out = mmr(cands, k=1)
    assert out[0].ref_id == "a"  # tie broken by lexicographic ref_id
