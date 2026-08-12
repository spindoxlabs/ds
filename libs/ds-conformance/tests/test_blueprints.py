from pathlib import Path

from ds_conformance.blueprints import find_orphan_ids, parse_blueprints
from ds_conformance.model import Force

HEADER = "| ID | Requirement | Force | Source |\n|---|---|---|---|\n"


def page(root: Path, name: str, body: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")


def test_requirement_rows_are_read(tmp_path: Path) -> None:
    page(
        tmp_path,
        "dssc/aup.md",
        HEADER + "| `DSSC-AUP-01` | convert business rules | must | §2 Capabilities |\n",
    )
    requirements, problems = parse_blueprints(tmp_path)
    assert problems == []
    assert len(requirements) == 1
    assert requirements[0].id == "DSSC-AUP-01"
    assert requirements[0].force is Force.MUST
    assert requirements[0].page == "dssc/aup.md"
    assert requirements[0].is_binding


def test_may_and_recommended_rows_are_read_but_not_binding(tmp_path: Path) -> None:
    page(
        tmp_path,
        "dssc/aup.md",
        HEADER
        + "| `DSSC-AUP-02` | an optional row | may | §2 |\n"
        + "| `DSSC-AUP-03` | a suggested row | recommended | §2 |\n"
        + "| `DSSC-AUP-04` | a should row | should | §2 |\n",
    )
    requirements, _ = parse_blueprints(tmp_path)
    binding = {r.id for r in requirements if r.is_binding}
    assert binding == {"DSSC-AUP-04"}


def test_a_duplicate_id_is_reported(tmp_path: Path) -> None:
    # The two rows may say different things and a manifest can answer only one.
    page(tmp_path, "a.md", HEADER + "| `DSSC-AUP-01` | first wording | must | §2 |\n")
    page(tmp_path, "b.md", HEADER + "| `DSSC-AUP-01` | second wording | should | §3 |\n")
    requirements, problems = parse_blueprints(tmp_path)
    assert len(requirements) == 1
    assert [p.kind for p in problems] == ["duplicate-requirement-id"]


def test_a_non_requirement_table_is_ignored(tmp_path: Path) -> None:
    page(
        tmp_path,
        "a.md",
        "| Standard | Version | Role | Normative force |\n|---|---|---|---|\n"
        "| ODRL | 2.2 | policy language | recommended |\n",
    )
    requirements, problems = parse_blueprints(tmp_path)
    assert requirements == []
    assert problems == []


def test_an_id_discussed_in_prose_but_never_declared_is_reported(tmp_path: Path) -> None:
    # Invisible to the coverage manifest, so invisible to the assessment —
    # exactly the class of gap this tool exists to surface.
    page(
        tmp_path,
        "a.md",
        HEADER
        + "| `DSSC-AUP-01` | declared | must | §2 |\n"
        + "\nSee also `DSSC-AUP-77`, which nothing declares.\n",
    )
    requirements, _ = parse_blueprints(tmp_path)
    orphans = find_orphan_ids(tmp_path, {r.id for r in requirements})
    assert [p.subject for p in orphans] == ["DSSC-AUP-77"]


def test_an_orphan_cited_many_times_is_reported_once(tmp_path: Path) -> None:
    page(tmp_path, "a.md", "`DSSC-AUP-77` and `DSSC-AUP-77` and again `DSSC-AUP-77`\n")
    orphans = find_orphan_ids(tmp_path, set())
    assert len(orphans) == 1


def test_the_real_blueprints_parse_completely() -> None:
    root = Path(__file__).resolve().parents[3] / "docs" / "blueprints"
    if not root.is_dir():  # pragma: no cover - only when run outside the repo
        return
    requirements, problems = parse_blueprints(root)
    assert requirements, "no requirements parsed from the real blueprints"
    structural = [
        p for p in problems if p.kind in {"malformed-requirement-row", "duplicate-requirement-id"}
    ]
    assert structural == [], f"blueprint rows the parser cannot see: {structural}"
    # Both blueprints are present and both carry binding rows.
    assert any(r.id.startswith("DSSC-") for r in requirements)
    assert any(r.id.startswith("CEEDS-") for r in requirements)


def test_informative_is_a_force_not_a_parse_failure(tmp_path: Path) -> None:
    # A third of the blueprint rows describe what a data space *is* rather than
    # obliging anybody. Bucketing them as "other" made 525 rows read as though
    # the scanner had given up on them.
    page(tmp_path, "a.md", HEADER + "| `DSSC-FND-01` | a description | informative | §1 |\n")
    requirements, problems = parse_blueprints(tmp_path)
    assert problems == []
    assert requirements[0].force is Force.INFORMATIVE
    assert not requirements[0].is_binding


def test_a_force_this_enum_has_not_learned_stays_distinct(tmp_path: Path) -> None:
    page(tmp_path, "a.md", HEADER + "| `DSSC-FND-02` | a row | conditional | §1 |\n")
    requirements, _ = parse_blueprints(tmp_path)
    assert requirements[0].force is Force.OTHER
