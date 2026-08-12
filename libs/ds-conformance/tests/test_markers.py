from pathlib import Path

from ds_conformance.markers import collect_flows, collect_java, collect_python, collect_ui
from ds_conformance.model import Layer


def make(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------


def test_a_function_marker_is_collected(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "connector" / "tests" / "test_consent.py",
        'import pytest\n\n\n@pytest.mark.rule("D-15")\n'
        "def test_opt_out_beats_the_wildcard() -> None:\n    pass\n",
    )
    evidence, problems = collect_python(tmp_path, [tmp_path / "services"])
    assert problems == []
    assert len(evidence) == 1
    assert evidence[0].rule_id == "D-15"
    assert evidence[0].unit == "services/connector"
    assert evidence[0].layer is Layer.UNIT
    assert evidence[0].node.endswith("::test_opt_out_beats_the_wildcard")


def test_one_test_may_evidence_several_rules(tmp_path: Path) -> None:
    make(
        tmp_path / "libs" / "governance" / "tests" / "test_mapper.py",
        'import pytest\n\n\n@pytest.mark.rule("A-6", "A-7")\n'
        "def test_secret_is_never_mapped() -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "libs"])
    assert sorted(e.rule_id for e in evidence) == ["A-6", "A-7"]


def test_the_bare_mark_spelling_is_understood(tmp_path: Path) -> None:
    # `from pytest import mark` is idiomatic and a collector that only knew the
    # dotted form would report a real test as missing.
    make(
        tmp_path / "libs" / "ds-auth" / "tests" / "test_verify.py",
        'from pytest import mark\n\n\n@mark.rule("P-3")\n'
        "def test_expiry_is_checked() -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "libs"])
    assert [e.rule_id for e in evidence] == ["P-3"]


def test_an_integration_test_is_labelled_as_one(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "identity-registry" / "tests" / "integration" / "test_live.py",
        'import pytest\n\n\n@pytest.mark.rule("P-1")\ndef test_enrolment() -> None:\n    pass\n',
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "services"])
    assert evidence[0].layer is Layer.INTEGRATION


def test_a_class_marker_reaches_every_test_in_the_class(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "provenance" / "tests" / "test_events.py",
        'import pytest\n\n\n@pytest.mark.rule("L-2")\nclass TestDisclosure:\n'
        "    def test_hash_is_required(self) -> None:\n        pass\n\n"
        "    def test_dataset_is_named(self) -> None:\n        pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "services"])
    assert len(evidence) == 2
    assert {e.rule_id for e in evidence} == {"L-2"}
    assert all("TestDisclosure::" in e.node for e in evidence)


def test_a_module_marker_covers_the_module(tmp_path: Path) -> None:
    make(
        tmp_path / "libs" / "governance" / "tests" / "test_profile.py",
        'import pytest\n\npytestmark = pytest.mark.rule("A-1")\n\n\n'
        "def test_broader_chain() -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "libs"])
    assert {e.rule_id for e in evidence} == {"A-1"}
    assert any(e.node.endswith("::<module>") for e in evidence)


def test_a_module_marker_in_a_list_is_understood(tmp_path: Path) -> None:
    make(
        tmp_path / "libs" / "governance" / "tests" / "test_profile.py",
        'import pytest\n\npytestmark = [pytest.mark.asyncio, pytest.mark.rule("A-2")]\n\n\n'
        "def test_child_does_not_cover_parent() -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "libs"])
    assert {e.rule_id for e in evidence} == {"A-2"}


def test_an_unrelated_marker_is_not_evidence(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "connector" / "tests" / "test_x.py",
        'import pytest\n\n\n@pytest.mark.integration\n@pytest.mark.parametrize("n", [1])\n'
        "def test_thing(n: int) -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "services"])
    assert evidence == []


def test_a_non_test_file_is_not_scanned(tmp_path: Path) -> None:
    # A marker in production code would be a claim with no runnable node behind
    # it, which is the thing this tool exists to refuse.
    make(
        tmp_path / "services" / "connector" / "src" / "helper.py",
        'import pytest\n\n\n@pytest.mark.rule("D-1")\n'
        "def test_looks_like_one() -> None:\n    pass\n",
    )
    evidence, _ = collect_python(tmp_path, [tmp_path / "services"])
    assert evidence == []


def test_an_unparseable_test_file_is_reported_not_ignored(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "connector" / "tests" / "test_broken.py",
        "def test_x(:\n",
    )
    evidence, problems = collect_python(tmp_path, [tmp_path / "services"])
    assert evidence == []
    assert [p.kind for p in problems] == ["unparseable-test-source"]


# --------------------------------------------------------------------------
# Java
# --------------------------------------------------------------------------


def test_a_java_tag_binds_to_the_method_below_it(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "edc-extensions" / "src" / "test" / "FailClosedTest.java",
        "class FailClosedTest {\n"
        '    @Test @Tag("rule:A-11")\n'
        "    void sustainedSilenceDenies() {\n    }\n"
        "    @Test\n"
        "    void unmarked() {\n    }\n"
        "}\n",
    )
    evidence = collect_java(tmp_path, [tmp_path / "services"])
    assert len(evidence) == 1
    assert evidence[0].rule_id == "A-11"
    assert evidence[0].node == "FailClosedTest#sustainedSilenceDenies"
    assert evidence[0].layer is Layer.JAVA


def test_a_tag_on_its_own_line_still_binds(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "edc-extensions" / "src" / "test" / "PolicyRegistrationTest.java",
        "class PolicyRegistrationTest {\n"
        '    @Tag("rule:A-14")\n'
        "    @Test\n"
        "    void everyBoundOperandHasAFunction() {\n    }\n"
        "}\n",
    )
    evidence = collect_java(tmp_path, [tmp_path / "services"])
    assert [e.node for e in evidence] == ["PolicyRegistrationTest#everyBoundOperandHasAFunction"]


def test_a_class_level_tag_names_the_class(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "edc-extensions" / "src" / "test" / "TtlCacheTest.java",
        '@Tag("rule:X-9")\nclass TtlCacheTest {\n    @Test\n    void expires() {\n    }\n}\n',
    )
    evidence = collect_java(tmp_path, [tmp_path / "services"])
    assert [(e.rule_id, e.node) for e in evidence] == [("X-9", "TtlCacheTest")]


def test_a_non_test_java_file_is_not_scanned(tmp_path: Path) -> None:
    make(
        tmp_path / "services" / "edc-extensions" / "src" / "main" / "Helper.java",
        '@Tag("rule:A-11")\nclass Helper {\n}\n',
    )
    assert collect_java(tmp_path, [tmp_path / "services"]) == []


# --------------------------------------------------------------------------
# ds-e2e flows
# --------------------------------------------------------------------------


def test_a_flow_declares_its_rules_and_is_cited_by_flow_name(tmp_path: Path) -> None:
    flows = tmp_path / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows"
    make(
        flows / "consent_withdrawal.py",
        "class ConsentWithdrawalFlow(Flow):\n"
        '    name = "consent-withdrawal"\n'
        '    rules = ("D-17", "CR-5")\n',
    )
    evidence, problems = collect_flows(tmp_path, flows)
    assert problems == []
    assert sorted(e.rule_id for e in evidence) == ["CR-5", "D-17"]
    # `task e2e:all` prints the flow name, so that is what a reader can run.
    assert {e.node for e in evidence} == {"consent-withdrawal"}
    assert {e.layer for e in evidence} == {Layer.E2E}


def test_a_flow_without_a_name_falls_back_to_the_class(tmp_path: Path) -> None:
    flows = tmp_path / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows"
    make(flows / "smoke.py", 'class SmokeFlow(Flow):\n    rules = ("X-1",)\n')
    evidence, _ = collect_flows(tmp_path, flows)
    assert [e.node for e in evidence] == ["SmokeFlow"]


def test_an_annotated_rules_attribute_is_understood(tmp_path: Path) -> None:
    flows = tmp_path / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows"
    make(
        flows / "uc1.py",
        'class Uc1Flow(Flow):\n    name: str = "uc1"\n    rules: tuple[str, ...] = ("C-1",)\n',
    )
    evidence, _ = collect_flows(tmp_path, flows)
    assert [(e.rule_id, e.node) for e in evidence] == [("C-1", "uc1")]


# --------------------------------------------------------------------------
# Playwright
# --------------------------------------------------------------------------


def test_a_playwright_title_tag_is_collected(tmp_path: Path) -> None:
    ui = tmp_path / "services" / "portal" / "tests" / "ui"
    make(
        ui / "viewer.spec.ts",
        "test('a viewer cannot write @rule:P-12', async ({ page }) => {\n});\n"
        "test('untagged journey', async ({ page }) => {\n});\n",
    )
    evidence = collect_ui(tmp_path, ui)
    assert len(evidence) == 1
    assert evidence[0].rule_id == "P-12"
    assert evidence[0].layer is Layer.UI
    assert evidence[0].unit == "services/portal"


def test_a_flow_file_that_will_not_parse_is_reported_not_skipped(tmp_path: Path) -> None:
    # An earlier version swallowed the SyntaxError and returned nothing for the
    # file, which reads as "this flow evidences no rule" — indistinguishable
    # from a flow that genuinely declares none. It hid thirteen broken files
    # behind a plausible zero.
    flows = tmp_path / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows"
    make(flows / "good.py", 'class GoodFlow(Flow):\n    name = "good"\n    rules = ("X-1",)\n')
    make(flows / "broken.py", "class BrokenFlow(Flow):\n    description = (\n    rules = (\n")
    evidence, problems = collect_flows(tmp_path, flows)
    assert [e.rule_id for e in evidence] == ["X-1"]
    assert [p.kind for p in problems] == ["unparseable-flow-source"]
    assert "broken.py" in problems[0].subject
