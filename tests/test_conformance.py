"""The ``fun-lab/*`` tables, run against THIS side, on BOTH stores.

``laravel-fun-lab`` (the reference: the goldens were exported from it) and
``@particle-academy/fancy-fun-lab`` run the identical rows from the identical
files. That is the whole mechanism: three runtimes read one table, so a
divergence is a red build in whichever one drifted.

Every table runs twice, once on ``InMemoryStore`` and once on ``SqliteStore``,
because the two stores are separate code paths and a row that only one of them
passes is a store that does not keep the contract.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fancy_conformance import cases, format_summary, run_table, version

from fancy_fun_lab import InMemoryStore, SqliteStore, Store, headline, slug

from .scenario_runner import run_scenario

#: Moved deliberately, never automatically. A pin that follows whatever is on
#: disk asserts nothing. CI checks out `ref: v<this>`; move the two together.
PINNED_SUITE_VERSION = "0.49.0"

#: Rows per suite at the pinned version: the vacuity guard.
SUITES = {
    "fun-lab/strings": 21,
    "fun-lab/progression": 17,
    "fun-lab/grants": 10,
    "fun-lab/leaderboard": 11,
    "fun-lab/analytics": 8,
}

STORES: dict[str, Callable[[], Store]] = {
    "memory": InMemoryStore,
    "sqlite": lambda: SqliteStore(":memory:"),
}


def _impl(store_factory: Callable[[], Store]) -> Callable[[dict[str, Any]], Any]:
    def run(case: dict[str, Any]) -> Any:
        fn = case["fn"]
        if fn == "slug":
            return slug(case["input"]["value"])
        if fn == "headline":
            return headline(case["input"]["value"])
        if fn == "scenario":
            return run_scenario(case["input"], store_factory)
        raise AssertionError(f"case {case['id']} calls unimplemented fn {fn}")

    return run


def test_the_pinned_fixture_version_is_what_is_on_disk() -> None:
    assert version() == PINNED_SUITE_VERSION, (
        f"fancy-conformance is at {version()}, this suite is pinned to "
        f"{PINNED_SUITE_VERSION}. Re-run the suites and move the pin deliberately."
    )


@pytest.mark.parametrize(("suite", "rows"), list(SUITES.items()))
def test_the_tables_are_not_empty(suite: str, rows: int) -> None:
    # A loader that resolves, returns nothing and reports "0 failed" reads
    # exactly like full coverage.
    assert len(cases(suite)) >= rows


@pytest.mark.parametrize("store", list(STORES))
@pytest.mark.parametrize("suite", list(SUITES))
def test_agrees_with_the_fun_lab_table(
    suite: str, store: str, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = run_table(suite, _impl(STORES[store]))
    with capsys.disabled():
        # Printed unconditionally, pass or fail.
        print(f"\n[{store}] " + format_summary(summary))
    assert summary["ok"], format_summary(summary)
    assert summary["passed"] >= SUITES[suite]


def _conformance_checkout_refs(workflow: str) -> list[str | None]:
    """The `ref:` of every workflow step that checks out fancy-conformance.

    Plain text on purpose: a YAML parser would be a dependency for one assertion.
    """
    lines = workflow.splitlines()
    refs: list[str | None] = []
    for index, line in enumerate(lines):
        start = re.match(r"(\s*)- ", line)
        if not start:
            continue
        step = [line]
        for following in lines[index + 1 :]:
            body = following.strip()
            indent = len(following) - len(following.lstrip())
            if body and not body.startswith("#") and indent <= len(start.group(1)):
                break
            step.append(following)
        text = "\n".join(step)
        if re.search(
            r"^\s*(- )?repository:\s*[\"']?Particle-Academy/fancy-conformance[\"']?\s*(#.*)?$",
            text,
            re.MULTILINE,
        ):
            ref = re.search(r"^\s*(- )?ref:\s*[\"']?([^\"'\s#]+)", text, re.MULTILINE)
            refs.append(ref.group(2) if ref else None)
    return refs


def test_the_checkout_ref_parser_sees_a_missing_ref() -> None:
    workflow = """
      - uses: actions/checkout@v4
        with:
          repository: Particle-Academy/fancy-conformance
          path: .fancy-conformance
      - name: Pinned
        uses: actions/checkout@v4
        with:
          repository: "Particle-Academy/fancy-conformance"
          ref: 'v1.2.3'  # a comment
    """
    assert _conformance_checkout_refs(workflow) == [None, "v1.2.3"]


def test_ci_checks_out_the_fixture_tag_this_suite_pins() -> None:
    here = Path(__file__).resolve()
    workflows = next(
        (p / ".github" / "workflows" for p in here.parents if (p / ".github/workflows").is_dir()),
        None,
    )
    assert workflows is not None, f"no .github/workflows above {here}"
    refs = {
        path.name: _conformance_checkout_refs(path.read_text(encoding="utf-8"))
        for path in sorted(workflows.glob("*.y*ml"))
    }
    refs = {name: found for name, found in refs.items() if found}
    assert refs, "no workflow checks out Particle-Academy/fancy-conformance"
    expected = f"v{PINNED_SUITE_VERSION}"
    for name, found in refs.items():
        assert found == [expected] * len(found), (
            f".github/workflows/{name} checks fancy-conformance out at {found}, but this "
            f"suite pins {PINNED_SUITE_VERSION}. Set `ref: {expected}` there."
        )
