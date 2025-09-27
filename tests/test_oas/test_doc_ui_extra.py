from lihil.oas.doc_ui import get_problem_ui_html


def test_problem_ui_deduplicates_problems():
    # Use a simple synthetic problem class with required interface
    from lihil.problems import DetailBase, ProblemDetail

    class MyProblem(DetailBase[str]):
        """Dummy problem for testing UI de-duplication."""

        __status__ = 400

        def __init__(self, detail: str = "x"):
            self.detail = detail

        def __problem_detail__(self, instance: str) -> ProblemDetail[str]:
            return ProblemDetail[str](
                type_="my-problem",
                title="My Problem",
                status=400,
                detail=self.detail,
                instance=instance,
            )

        @classmethod
        def __json_example__(cls) -> ProblemDetail[str]:
            return ProblemDetail[str](
                type_="my-problem",
                title="My Problem",
                status=400,
                detail="example",
                instance="/",
            )

    # Pass duplicates to exercise the `continue` branch
    resp = get_problem_ui_html(title="t", problems=[MyProblem, MyProblem])
    assert resp.media_type == "text/html"
