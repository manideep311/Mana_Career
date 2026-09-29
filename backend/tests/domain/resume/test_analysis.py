from app.domain.resume.analysis import TargetSpec, analyze_resume

STRONG = """Jordan Rivera
jordan@example.com | +1 555 010 0199
SUMMARY
Data analyst focused on turning messy operational data into decisions.
EXPERIENCE
Data Analyst, Northwind Traders 2021 - Present
• Built SQL dashboards in Tableau used by 40 regional managers every week
• Automated weekly reporting with Python and pandas, saving 6 hours a week
• Reduced month-end reconciliation errors by 30% with validation checks in Excel
Operations Assistant, Contoso 2019 - 2021
• Led a pricing review across 120 stores that cut discount leakage by 12%
EDUCATION
BSc Statistics, State University 2019
SKILLS
Python, SQL, Tableau, Excel, pandas, statistics
"""

WEAK = """Sam Lee
EXPERIENCE
Marketing Coordinator, Acme 2020 - 2023
- Responsible for managing the social media accounts and posting content regularly
- Helped the team with campaign planning and various other marketing activities
- Worked on the monthly newsletter and coordinated with designers on layouts
SKILLS
Python, Docker, Kubernetes, TensorFlow, SQL
"""


def _ids(analysis):
    return [i.id for i in analysis.issues]


def test_strong_resume_is_recognised():
    a = analyze_resume(STRONG, page_count=1)
    assert all(a.sections[s] for s in ("contact", "summary", "experience", "education", "skills"))
    assert a.bullet_count == 4 and a.bullets_with_results == 4
    assert any("measurable result" in s for s in a.strengths)
    assert any("in action" in s for s in a.strengths)
    assert not [i for i in a.issues if i.severity == "high"]


def test_skill_evidence_distinguishes_applied_from_listed():
    a = analyze_resume(STRONG)
    by_slug = {s.slug: s for s in a.skills}
    assert by_slug["python"].applied
    assert any("pandas" in line for line in by_slug["python"].lines)


def test_weak_resume_gets_specific_grounded_issues():
    a = analyze_resume(WEAK)
    ids = _ids(a)
    assert "few_results" in ids
    assert "weak_openings" in ids
    assert "missing_contact" in ids
    assert "skills_without_evidence" in ids
    few = next(i for i in a.issues if i.id == "few_results")
    # Examples quote the user's own lines, never invented text.
    assert all(ex in WEAK for ex in few.examples)
    # Issues come highest severity first.
    order = {"high": 0, "medium": 1, "low": 2}
    assert [order[i.severity] for i in a.issues] == sorted(order[i.severity] for i in a.issues)


def test_every_issue_has_problem_reason_and_suggestion():
    for text in (STRONG, WEAK):
        for issue in analyze_resume(text).issues:
            assert issue.problem and issue.why_it_matters and issue.suggestion


def test_years_alone_do_not_count_as_results():
    bullet = "• Joined the analytics team in 2020 and supported quarterly planning\n"
    text = ("EXPERIENCE\nAnalyst 2020 - 2022\n" + bullet) * 3
    a = analyze_resume(text + "x " * 40)
    assert a.bullets_with_results == 0


def test_target_alignment_never_suggests_claiming_missing_skills():
    target = TargetSpec("Data Engineer", (("sql", "SQL"), ("python", "Python"),
                                          ("apache-airflow", "Apache Airflow"),
                                          ("apache-kafka", "Apache Kafka")))
    a = analyze_resume(STRONG, target=target)
    assert a.alignment is not None
    assert set(a.alignment.evidenced) == {"SQL", "Python"}
    gap = next(i for i in a.issues if i.id == "target_keywords_missing")
    assert "skill gaps" in gap.suggestion  # honest: not "just add the word"


def test_unreadable_text_is_reported_not_guessed():
    a = analyze_resume("Page 1")
    assert not a.enough_text
    assert _ids(a) == ["not_enough_text"]
