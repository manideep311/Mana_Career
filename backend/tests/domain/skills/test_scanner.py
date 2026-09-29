from app.domain.skills.scanner import scan_lines, scan_text


def test_finds_skills_with_their_evidence_lines():
    hits = scan_text(
        "Built SQL dashboards in Tableau for 40 managers\n"
        "Automated weekly reporting with Python and pandas\n"
        "Skills: Python, SQL, Excel"
    )
    assert {"sql", "python", "pandas"} <= set(hits)
    assert hits["python"].lines == [
        "Automated weekly reporting with Python and pandas",
        "Skills: Python, SQL, Excel",
    ]
    assert hits["sql"].mentions == 2


def test_symbol_names_match():
    hits = scan_text("Services in C++ and C#; APIs on Node.js")
    assert {"c++", "c#"} <= set(hits)


def test_ambiguous_short_aliases_do_not_match_prose():
    hits = scan_text("Please see my CV. I go to meetups and write es modules on pg 3.")
    assert not {"computer-vision", "go", "elasticsearch", "postgresql"} & set(hits)


def test_common_word_skills_need_their_capitalisation():
    assert "express" not in scan_text("I like to express ideas clearly")
    assert "express" in scan_text("REST APIs built with Express and PostgreSQL")
    assert "go" not in scan_text("Ready to go live next week")
    assert "go" in scan_text("Backend services in Go and Python")


def test_single_letter_skills_only_inside_a_skill_list():
    assert "r" not in scan_text("Signed, R. Smith")
    assert "r" in scan_text("Languages: Python, R, SQL")


def test_aliases_resolve_to_the_canonical_skill():
    hits = scan_lines(["Deployed to k8s with Terraform", "Golang microservices"])
    assert "terraform" in hits
    assert "go" in hits  # via the "golang" alias


def test_skill_name_inside_a_longer_word_does_not_match():
    assert "java" not in scan_text("Wrote JavaScript for the dashboard")
