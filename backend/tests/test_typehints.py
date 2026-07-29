import textwrap

from backend.services import typehints


def dedent(code: str) -> str:
    return textwrap.dedent(code)


def coverage_of(source: str) -> float:
    return typehints.analyze_file("f.py", dedent(source))["coverage"]


def test_fully_annotated_function_is_100_percent():
    assert coverage_of("""
        def add(a: int, b: int) -> int:
            return a + b
    """) == 100.0


def test_unannotated_function_is_0_percent():
    assert coverage_of("""
        def add(a, b):
            return a + b
    """) == 0.0


def test_partial_annotation_counts_each_slot():
    # 3 slots (a, b, return); only `a` is annotated.
    assert coverage_of("""
        def add(a: int, b):
            return a + b
    """) == round(1 / 3 * 100, 1)


def test_return_annotation_alone_counts():
    assert coverage_of("def now() -> str:\n    return ''\n") == 100.0


def test_self_and_cls_are_excluded():
    # Only the return slot exists once `self` is discounted, so this is complete.
    assert coverage_of("""
        class Thing:
            def describe(self) -> str:
                return "thing"
    """) == 100.0


def test_self_exclusion_does_not_hide_real_parameters():
    report = typehints.analyze_file("f.py", dedent("""
        class Thing:
            def rename(self, name):
                self.name = name
    """))
    assert report["functions"][0]["parameters"] == 1
    assert report["coverage"] == 0.0


def test_varargs_and_kwargs_are_annotatable():
    assert coverage_of("""
        def call(*args: int, **kwargs: str) -> None:
            return None
    """) == 100.0


def test_keyword_only_arguments_are_counted():
    assert coverage_of("""
        def build(*, name, size: int) -> str:
            return name * size
    """) == round(2 / 3 * 100, 1)


def test_methods_are_labelled_with_their_class():
    report = typehints.analyze_file("f.py", dedent("""
        class Repo:
            def clone(self) -> None:
                pass
    """))
    assert report["functions"][0]["name"] == "Repo.clone"


def test_async_functions_are_included():
    report = typehints.analyze_file("f.py", dedent("""
        async def fetch(url: str) -> bytes:
            return b""
    """))
    assert report["function_count"] == 1
    assert report["coverage"] == 100.0


def test_typed_counts_are_split_three_ways():
    report = typehints.analyze_file("f.py", dedent("""
        def full(a: int) -> int:
            return a

        def partial(a: int, b):
            return a

        def none(a, b):
            return a
    """))
    assert (report["fully_typed"], report["partially_typed"], report["untyped"]) == (1, 1, 1)


def test_annotated_variables_are_counted():
    report = typehints.analyze_file("f.py", "count: int = 0\n")
    assert report["annotated_variables"] == 1


def test_syntax_error_yields_empty_report():
    report = typehints.analyze_file("f.py", "def broken(:\n")
    assert report["function_count"] == 0
    assert report["rating"] == "Poor"


def test_file_with_no_functions_is_100_percent():
    assert coverage_of("VALUE = 1\n") == 100.0


# ---------------------------------------------------------------------------
# ratings + repository aggregation
# ---------------------------------------------------------------------------

def test_rating_bands():
    assert typehints.rate(95.0) == "Excellent"
    assert typehints.rate(75.0) == "Good"
    assert typehints.rate(50.0) == "Fair"
    assert typehints.rate(10.0) == "Poor"


def test_repository_coverage_pools_slots_rather_than_averaging_files():
    # One large untyped file must outweigh one tiny typed file.
    typed = "def a(x: int) -> int:\n    return x\n"
    untyped = "".join(f"def f{i}(a, b, c):\n    return a\n\n" for i in range(10))
    report = typehints.analyze([("small.py", typed), ("big.py", untyped)])

    naive_average = (100.0 + 0.0) / 2
    assert report["coverage"] < naive_average
    assert report["total_slots"] == 2 + 10 * 4


def test_lowest_files_lists_worst_first():
    report = typehints.analyze([
        ("good.py", "def a(x: int) -> int:\n    return x\n\ndef b(y: int) -> int:\n    return y\n"),
        ("bad.py", "def c(x):\n    return x\n\ndef d(y):\n    return y\n"),
    ])
    assert report["lowest_files"][0]["file_path"] == "bad.py"


def test_untyped_public_functions_are_surfaced():
    report = typehints.analyze([
        ("api.py", "def public_call(a, b, c):\n    return a\n\ndef _private(a):\n    return a\n"),
    ])
    names = {fn["name"] for fn in report["untyped_public_functions"]}
    assert names == {"public_call"}


def test_files_without_functions_are_omitted_from_the_table():
    report = typehints.analyze([("consts.py", "X = 1\n"), ("api.py", "def a(x: int) -> int:\n    return x\n")])
    assert [f["file_path"] for f in report["files"]] == ["api.py"]
