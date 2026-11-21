import uuid
from datetime import UTC, datetime

from pagercutie.alerts.schemas import StepStatus
from pagercutie.pipeline.executor.stage import StepJob
from pagercutie.runbooks.steps import Wait


def job(failures_by_index: dict[int, int]) -> StepJob:
    return StepJob(
        run_id=uuid.uuid4(),
        index=1,
        alert_id=uuid.uuid4(),
        team_id=None,
        step=Wait(action="wait", seconds=5),
        status=StepStatus.PENDING,
        guard_answered=False,
        approved=False,
        attempts=0,
        failures_by_index=failures_by_index,
        occurrences=1,
        occurrences_at_run=None,
        event={},
        lease=datetime(2026, 11, 21, tzinfo=UTC),
    )


def test_failures_reads_the_mapped_count_and_is_zero_for_a_missing_index() -> None:
    state = job({0: 2})

    assert state.failures(0) == 2
    assert state.failures(1) == 0
