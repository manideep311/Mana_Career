from app.domain.matching.scorer import JobSnapshot, ProfileSnapshot, inputs_hash, score


def _profile(**kw) -> ProfileSnapshot:
    base = dict(
        skill_ids=frozenset(), skill_labels=(), tech=frozenset(), titles=(),
        project_tech=frozenset(), has_degree=False, fields=(), seniority=None,
        years_experience=None, preferred_roles=(), locations=(), work_modes=frozenset(),
        salary_min=None, summary_text="",
    )
    base.update(kw)
    return ProfileSnapshot(**base)


def _job(**kw) -> JobSnapshot:
    base = dict(
        required=(), preferred=(), skill_labels=(), title="", seniority=None,
        exp_min=None, exp_max=None, location=None, work_mode=None,
        salary_min=None, salary_max=None, chunk_embeddings=(),
    )
    base.update(kw)
    return JobSnapshot(**base)


def _comp(result, name):
    return next(c for c in result.components if c.dimension == name)


# --------------------------------------------------------------------------- #
# per-dimension behaviour
# --------------------------------------------------------------------------- #
def test_skill_dimension_weighted_coverage():
    p = _profile(skill_ids=frozenset({"a", "b"}))
    j = _job(required=(("a", 1.0), ("b", 1.0), ("c", 1.0)))
    r = score(p, j)
    skill = next(c for c in r.components if c.dimension == "skill")
    # raw_score is round(raw, 3) per spec, so 2/3 lands at 0.667
    assert abs(skill.raw_score - 2 / 3) < 1e-3
    assert skill.detail["missing"] == ["c"]
    assert skill.detail["matched"] == ["a", "b"]
    assert [e["ref_id"] for e in skill.evidence] == ["a", "b"]


def test_skill_preferred_bonus_and_empty_required():
    # no required, no preferred -> full credit
    assert _comp(score(_profile(), _job()), "skill").raw_score == 1.0
    # preferred-only, half covered -> 0.3 * 0.5
    p = _profile(skill_ids=frozenset({"x"}))
    j = _job(preferred=(("x", 1.0), ("y", 1.0)))
    assert _comp(score(p, j), "skill").raw_score == round(0.3 * 0.5, 3)
    # required fully covered plus a preferred hit -> capped at 1.0
    p2 = _profile(skill_ids=frozenset({"a", "z"}))
    j2 = _job(required=(("a", 1.0),), preferred=(("z", 1.0),))
    assert _comp(score(p2, j2), "skill").raw_score == 1.0


def test_experience_years_and_title_overlap():
    p = _profile(years_experience=8.0, titles=("senior backend engineer",))
    j = _job(exp_min=5, title="senior backend engineer")
    exp = _comp(score(p, j), "experience")
    assert exp.raw_score == 1.0  # years_part 1.0, title_part 1.0
    assert exp.detail["job_exp_min"] == 5
    # under-experienced, no title overlap -> 0.6 * (2/5) + 0.4 * 0
    exp2 = _comp(score(_profile(years_experience=2.0), _job(exp_min=5)), "experience")
    assert exp2.raw_score == round(0.6 * (2 / 5), 3)
    # no job floor at all -> years_part defaults to 1.0
    exp3 = _comp(score(_profile(), _job()), "experience")
    assert exp3.raw_score == round(0.6, 3)


def test_technology_token_overlap_fraction():
    p = _profile(tech=frozenset({"python", "django"}))
    j = _job(skill_labels=("Python", "Kubernetes"))
    tech = _comp(score(p, j), "technology")
    assert tech.raw_score == 0.5  # 1 of {python, kubernetes}
    assert tech.detail["overlap"] == ["python"]
    assert tech.detail["job_only"] == ["kubernetes"]


def test_semantic_neutral_without_embeddings_then_cosine():
    r0 = score(_profile(), _job())
    assert next(c for c in r0.components if c.dimension == "semantic").raw_score == 0.5
    vec = tuple(1.0 if i == 0 else 0.0 for i in range(8))
    r1 = score(_profile(summary_text="x"), _job(chunk_embeddings=(vec,)), profile_embedding=vec)
    assert next(c for c in r1.components if c.dimension == "semantic").raw_score == 1.0


def test_role_best_jaccard_over_preferred_roles():
    p = _profile(preferred_roles=("data analyst", "data scientist"))
    j = _job(title="senior data scientist")
    # job tokens {senior, data, scientist}: "data scientist" -> 2/3, "data analyst" -> 1/4
    assert _comp(score(p, j), "role").raw_score == round(2 / 3, 3)
    assert _comp(score(_profile(), j), "role").raw_score == 0.5  # no preferred roles


def test_seniority_ordinal_distance():
    r = score(_profile(seniority="junior"), _job(seniority="staff"))
    sr = next(c for c in r.components if c.dimension == "seniority").raw_score
    assert abs(sr - (1 - 3 / 5)) < 1e-6
    # missing either side -> neutral 0.5
    assert _comp(score(_profile(), _job(seniority="staff")), "seniority").raw_score == 0.5


def test_project_tech_overlap_tiers():
    j = _job(skill_labels=("python", "spark"))
    hit = _comp(score(_profile(project_tech=frozenset({"spark"})), j), "project")
    assert hit.raw_score == 1.0
    assert hit.detail["project_tech_overlap"] == ["spark"]
    miss = _comp(score(_profile(project_tech=frozenset({"rust"})), j), "project")
    assert miss.raw_score == 0.4  # has project tech, no overlap
    none_ = _comp(score(_profile(), j), "project")
    assert none_.raw_score == 0.0  # no project tech at all
    neutral = _comp(score(_profile(project_tech=frozenset({"rust"})), _job()), "project")
    assert neutral.raw_score == 0.5  # job carries no skill labels


def test_education_degree_and_field_match():
    deg = _comp(score(_profile(has_degree=True), _job(title="backend engineer")), "education")
    assert deg.raw_score == 0.6
    both = _comp(
        score(
            _profile(has_degree=True, fields=("computer science",)),
            _job(title="computer science lecturer"),
        ),
        "education",
    )
    assert both.raw_score == 1.0  # 0.6 + 0.4 field-token hit
    no = _comp(score(_profile(), _job(title="backend engineer")), "education")
    assert no.raw_score == 0.2


def test_location_remote_mode_and_place():
    assert _comp(score(_profile(), _job(work_mode="remote")), "location").raw_score == 1.0
    mode = _comp(
        score(_profile(work_modes=frozenset({"hybrid"})), _job(work_mode="hybrid")), "location"
    )
    assert mode.raw_score == 1.0
    place = _comp(
        score(_profile(locations=("berlin",)), _job(location="berlin, germany")), "location"
    )
    assert place.raw_score == 1.0
    assert _comp(score(_profile(), _job()), "location").raw_score == 0.5
    miss = _comp(
        score(_profile(work_modes=frozenset({"remote"})), _job(work_mode="onsite")), "location"
    )
    assert miss.raw_score == 0.3


def test_salary_range_clears_floor():
    ok = _comp(
        score(_profile(salary_min=120_000), _job(salary_min=110_000, salary_max=160_000)),
        "salary",
    )
    assert ok.raw_score == 1.0
    low = _comp(score(_profile(salary_min=200_000), _job(salary_max=150_000)), "salary")
    assert low.raw_score == round(150_000 / 200_000, 3)
    assert _comp(score(_profile(), _job(salary_max=150_000)), "salary").raw_score == 0.5


# --------------------------------------------------------------------------- #
# aggregation, bands, determinism, hash
# --------------------------------------------------------------------------- #
def test_aggregation_score_band_and_strengths():
    p = _profile(
        skill_ids=frozenset({"a"}), seniority="senior", years_experience=6.0,
        work_modes=frozenset({"remote"}), has_degree=True, preferred_roles=("ml engineer",),
        tech=frozenset({"python", "pytorch"}), project_tech=frozenset({"python"}),
    )
    j = _job(
        required=(("a", 1.0),), skill_labels=("python", "pytorch"), title="ml engineer",
        seniority="senior", exp_min=5, work_mode="remote",
    )
    r = score(p, j)
    assert 0 <= r.score <= 100
    assert r.band in {"strong", "good", "partial", "weak"}
    assert abs(r.score - sum(c.contribution for c in r.components)) < 0.01
    assert {c.dimension for c in r.components} == set(r.dimension_scores)
    assert all(s["raw_score"] >= 0.7 for s in r.strengths)
    assert len(r.strengths) <= 3
    assert len(r.gaps) <= 4
    # this profile/job pair is a strong match
    assert r.band == "strong"
    assert [c.dimension for c in r.components] == [
        "skill", "experience", "technology", "semantic", "role",
        "seniority", "project", "education", "location", "salary",
    ]


def test_gaps_are_low_scoring_dimensions_by_weight():
    # empty profile vs a demanding job: many dimensions fall below 0.5
    j = _job(
        required=(("a", 1.0), ("b", 1.0)), skill_labels=("go", "kafka"),
        title="staff platform engineer", seniority="staff", exp_min=8,
        work_mode="onsite", salary_min=90_000, salary_max=100_000,
    )
    r = score(_profile(salary_min=200_000), j)
    gap_dims = [g["dimension"] for g in r.gaps]
    assert gap_dims[0] == "skill"  # heaviest weight among the gaps
    assert all(g["raw_score"] < 0.5 for g in r.gaps)
    # weights are non-increasing across the ordered gap list
    weights = [g["weight"] for g in r.gaps]
    assert weights == sorted(weights, reverse=True)


def test_score_is_deterministic_and_hash_stable():
    p, j = _profile(skill_ids=frozenset({"a"})), _job(required=(("a", 1.0),))
    assert score(p, j) == score(p, j)
    h1 = inputs_hash(p, j)
    assert h1 == inputs_hash(p, j)
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)
    # summary_text is part of the hash; a different profile summary -> different hash
    assert inputs_hash(_profile(summary_text="a"), j) != inputs_hash(_profile(summary_text="b"), j)
    # job embeddings are part of the hash too
    v = tuple(1.0 if i == 0 else 0.0 for i in range(4))
    assert inputs_hash(p, j) != inputs_hash(p, _job(required=(("a", 1.0),), chunk_embeddings=(v,)))
