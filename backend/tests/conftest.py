def pytest_addoption(parser):
    parser.addoption(
        "--update-aligner-baseline",
        action="store_true",
        default=False,
        help="Update realignment_baseline.json from the current aligner instead of asserting against"
        "it. Run this after intentional aligner changes or test/fixture changes and commit the diff.",
    )
