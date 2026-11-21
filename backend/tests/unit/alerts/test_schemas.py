import pytest

from pagercutie.alerts.schemas import StepDecisionKind, StepStatus, expected_status


@pytest.mark.parametrize(
    ("decision", "status"),
    [
        (StepDecisionKind.APPROVE, StepStatus.AWAITING_APPROVAL),
        (StepDecisionKind.REJECT, StepStatus.AWAITING_APPROVAL),
        (StepDecisionKind.YES, StepStatus.AWAITING_ANSWER),
        (StepDecisionKind.NO, StepStatus.AWAITING_ANSWER),
        (StepDecisionKind.DONE, StepStatus.AWAITING_MANUAL),
    ],
)
def test_expected_status(decision: StepDecisionKind, status: StepStatus) -> None:
    assert expected_status(decision) is status
