import click
from typing import Set, Dict

from ci.ray_ci.utils import logger, ci_init
from ray_release.configs.global_config import get_global_config
from ray_release.test import Test
from ray_release.result import ResultStatus

LINUX_PYTHON_TEST_PREFIX = "linux:__python"


@click.command()
@click.argument("team", required=True, type=str)
@click.argument("coverage", required=True, type=int)
@click.option("--test-history-length", default=100, type=int)
@click.option("--test-prefix", default=LINUX_PYTHON_TEST_PREFIX, type=str)
def main(team: str, coverage: int, test_history_length: int, test_prefix: str) -> None:
    """
    This script determines the tests that need to be run to cover a certain percentage
    of PR failures, based on historical data
    """
    ci_init()
    tests = [
        test for test in Test.gen_from_s3(test_prefix) if test.get_oncall() == team
    ]
    logger.info(f"Analyzing {len(tests)} tests for team {team}")

    test_to_prs = {
        test.get_name(): _get_failed_prs(test, test_history_length) for test in tests
    }
    high_impact_tests = _get_test_with_minimal_coverage(test_to_prs, coverage)

    logger.info(
        f"To cover {coverage}% of PRs, run the following tests: {high_impact_tests}"
    )


def _get_test_with_minimal_coverage(
    test_to_prs: Dict[str, Set[str]], coverage: int
) -> Set[str]:
    """
    Get the minimal set of tests that cover a certain percentage of PRs
    """
    all_prs = set()
    high_impact_tests = set()
    for prs in test_to_prs.values():
        all_prs.update(prs)

    tests_sorted_by_impact = sorted(
        test_to_prs.keys(), key=lambda test: len(test_to_prs[test]), reverse=True
    )
    covered_prs = set()
    for test in tests_sorted_by_impact:
        covered_prs.update(test_to_prs[test])
        high_impact_tests.add(test)
        if 100 * len(covered_prs) / len(all_prs) >= coverage:
            break

    return high_impact_tests


def _get_failed_prs(test: Test, test_history_length: int) -> Set[str]:
    """
    Get the failed PRs for a test
    """
    logger.info(f"Analyzing test {test.get_name()}")
    results = [
        result
        for result in test.get_test_results(
            limit=test_history_length,
            aws_bucket=get_global_config()["state_machine_pr_aws_bucket"],
        )
        if result.status == ResultStatus.ERROR.value
    ]
    return {result.branch for result in results if result.branch}


if __name__ == "__main__":
    main()
