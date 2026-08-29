"""Running independent agent work at the same time.

The pipeline's two long loops — a crew run per concept, a render per variant —
were sequential, and both are almost entirely time spent waiting on a vendor
socket. Measured on 2026-08-27 against real runs: generate took 2096s for three
concepts, render 913s for eight variants. Nothing in either loop reads what the
previous iteration produced.
"""

import threading
import time

import pytest

from app.agents.parallel import in_parallel


class TestOrderIsPreserved:
    """Submission order, not completion order.

    Variants are persisted in this order and shown in it, so a fast job
    overtaking a slow one must not reorder the campaign's work.
    """

    def test_results_come_back_in_the_order_the_jobs_were_given(self):
        done, failure = in_parallel(
            [0.03, 0.01, 0.02],
            lambda delay: (time.sleep(delay), delay)[1],
            lanes=3,
        )
        assert [result for _, result in done] == [0.03, 0.01, 0.02]
        assert failure is None

    def test_each_result_carries_the_index_of_the_job_that_made_it(self):
        done, _ = in_parallel(["a", "b", "c"], str.upper, lanes=3)
        assert done == [(0, "A"), (1, "B"), (2, "C")]

    def test_an_empty_job_list_is_not_an_error(self):
        assert in_parallel([], str.upper, lanes=3) == ([], None)


class TestTheyActuallyOverlap:
    def test_three_waiting_jobs_take_about_as_long_as_one(self):
        """The whole point. A sequential loop would take 0.3s here."""
        started = time.time()
        in_parallel([0.1, 0.1, 0.1], time.sleep, lanes=3)
        assert time.time() - started < 0.25

    def test_lanes_bound_how_many_run_at_once(self):
        """Vendors rate-limit. Unbounded fan-out on nine variants is how a
        render pass turns into nine 429s instead of nine creatives."""
        live = 0
        peak = 0
        guard = threading.Lock()

        def job(_):
            nonlocal live, peak
            with guard:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with guard:
                live -= 1

        in_parallel(list(range(6)), job, lanes=2)
        assert peak <= 2

    def test_a_single_lane_is_the_old_sequential_loop(self):
        """So the concurrency can be turned off in one setting if a vendor
        starts refusing, without reverting to different code."""
        order = []
        in_parallel([0.03, 0.01], lambda d: (time.sleep(d), order.append(d)), lanes=1)
        assert order == [0.03, 0.01]


class TestAFailureKeepsWhatSucceeded:
    """A vendor error must never discard work already paid for."""

    def test_the_successes_are_returned(self):
        def job(n):
            if n == 1:
                raise RuntimeError("the vendor said no")
            return n * 10

        done, failure = in_parallel([0, 1, 2], job, lanes=1)
        assert (0, 0) in done
        assert isinstance(failure, RuntimeError)

    def test_the_failure_is_handed_back_rather_than_raised(self):
        """The caller has a half-finished run to persist first. Raising here
        would strand it."""
        done, failure = in_parallel([1], lambda _: 1 / 0, lanes=1)
        assert done == []
        assert isinstance(failure, ZeroDivisionError)

    def test_the_first_failure_by_position_is_the_one_reported(self):
        """Deterministic across runs: a race deciding which error a person is
        shown makes the same broken run tell two different stories."""

        def job(n):
            time.sleep(0.05 if n == 1 else 0)
            raise RuntimeError(f"job {n}")

        _, failure = in_parallel([1, 2], job, lanes=2)
        assert str(failure) == "job 1"

    def test_work_not_yet_started_is_abandoned_after_a_failure(self):
        """Sequential code stopped at the first error and the next run picked
        up the rest. Pressing on would spend vendor calls on a pass already
        known to be broken."""
        ran = []

        def job(n):
            ran.append(n)
            if n == 0:
                raise RuntimeError("stop")
            time.sleep(0.02)

        in_parallel(list(range(8)), job, lanes=1)
        assert len(ran) < 8


class TestLanesAreClamped:
    def test_zero_lanes_still_runs_the_work(self):
        """A misconfigured setting must not silently render nothing."""
        done, _ = in_parallel([1, 2], lambda n: n, lanes=0)
        assert [result for _, result in done] == [1, 2]

    def test_more_lanes_than_jobs_is_harmless(self):
        done, _ = in_parallel([1], lambda n: n, lanes=64)
        assert [result for _, result in done] == [1]


class TestAbandonedJobsAreNotMistakenForFailures:
    """A job that never ran did not fail, and must not be reported as one.

    `concurrent.futures.CancelledError` has moved between `Exception` and
    `BaseException` across Python versions, so a cancelled future is
    recognised by asking `future.cancelled()` rather than by catching what
    `.result()` throws.
    """

    def test_the_reported_failure_is_the_real_one(self):
        def job(n):
            if n == 0:
                raise RuntimeError("the only real failure")
            time.sleep(0.02)

        _, failure = in_parallel(list(range(8)), job, lanes=1)
        assert str(failure) == "the only real failure"

    def test_cancelling_does_not_raise_out_of_the_helper(self):
        def job(n):
            if n == 0:
                raise RuntimeError("stop")
            time.sleep(0.02)

        done, _ = in_parallel(list(range(8)), job, lanes=1)
        assert done == []
