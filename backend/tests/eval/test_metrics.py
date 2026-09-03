import math

from eval.metrics import mrr, ndcg_at_k, precision_at_k, recall_at_k


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c"], {"a", "d"}, 2) == 0.5
    assert recall_at_k(["a"], set(), 5) == 0.0
    assert recall_at_k(["x", "y"], {"x", "y"}, 10) == 1.0


def test_precision_at_k():
    assert precision_at_k(["a", "b", "c", "d"], {"a", "c"}, 4) == 0.5
    assert precision_at_k([], {"a"}, 0) == 0.0


def test_mrr():
    assert mrr(["z", "a", "b"], {"a"}) == 0.5
    assert mrr(["a"], {"a"}) == 1.0
    assert mrr(["x", "y"], {"a"}) == 0.0


def test_ndcg_at_k_perfect_is_one():
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 2) == 1.0


def test_ndcg_at_k_partial():
    # relevant at rank 2 only: DCG = 1/log2(3); IDCG (1 relevant) = 1/log2(2) = 1
    got = ndcg_at_k(["x", "a", "y"], {"a"}, 3)
    assert math.isclose(got, 1.0 / math.log2(3), rel_tol=1e-9)


def test_ndcg_at_k_no_relevant():
    assert ndcg_at_k(["a", "b"], set(), 2) == 0.0
