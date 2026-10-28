from datetime import UTC, datetime, timedelta

import pytest

from synapse_api.domain.enums import Casquette, Role, TaskStatus, TaskType
from synapse_api.domain.lifecycle import (
    Actor,
    AwaitingReason,
    Command,
    LifecycleError,
    PendingDecision,
    TaskState,
    apply,
    pending_decision,
)
from synapse_api.domain.rules import MAX_QA_ROUND_TRIPS, MAX_TASK_EXECUTION

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
PO = Actor.human("Aline Mbarga", Role.PO)
TESTEUR = Actor.human("Brice Nkoulou", Role.TESTEUR)
ADMIN = Actor.human("Admin", Role.ADMIN)
ORCH = Actor.agent(Casquette.ORCHESTRATEUR)
ARCHI = Actor.agent(Casquette.ARCHITECTE)


def run(state: TaskState, *steps: tuple[Command, Actor], now: datetime = NOW) -> TaskState:
    for command, actor in steps:
        state = apply(state, command, actor, now=now, comment="ok")
    return state


def in_progress(task_type: TaskType = TaskType.FEATURE) -> TaskState:
    return run(
        TaskState(task_type),
        (Command.PRIORITIZE, PO),
        (Command.PROPOSE_PLAN, ARCHI),
        (Command.VALIDATE_PLAN, PO),
    )


def in_review(task_type: TaskType = TaskType.FEATURE) -> TaskState:
    return run(in_progress(task_type), (Command.SUBMIT_FOR_REVIEW, ORCH))


def expect_error(code: str, state: TaskState, command: Command, actor: Actor, **kw) -> None:
    with pytest.raises(LifecycleError) as exc:
        apply(state, command, actor, now=kw.pop("now", NOW), comment=kw.pop("comment", "ok"))
    assert exc.value.code == code


class TestNominalPath:
    def test_feature_goes_from_backlog_to_done(self):
        state = run(in_review(), (Command.VALIDATE_RESULT, PO))
        assert state.status is TaskStatus.DONE

    def test_validating_plan_starts_execution_clock(self):
        state = in_progress()
        assert state.status is TaskStatus.IN_PROGRESS
        assert state.execution_started_at == NOW
        assert state.validated_plan_version == 1

    def test_bugfix_needs_tester_confirmation_after_po_validation(self):
        state = run(in_review(TaskType.BUGFIX), (Command.VALIDATE_RESULT, PO))
        assert state.status is TaskStatus.REVIEW
        state = run(state, (Command.CONFIRM_FIX, TESTEUR))
        assert state.status is TaskStatus.DONE

    def test_bugfix_tester_may_confirm_before_po(self):
        state = run(in_review(TaskType.BUGFIX), (Command.CONFIRM_FIX, TESTEUR))
        assert state.status is TaskStatus.REVIEW
        state = run(state, (Command.VALIDATE_RESULT, PO))
        assert state.status is TaskStatus.DONE


class TestHumanValidation:
    @pytest.mark.parametrize(
        "command",
        [Command.PRIORITIZE, Command.VALIDATE_PLAN, Command.VALIDATE_RESULT, Command.REJECT_RESULT],
    )
    def test_agents_never_take_human_decisions(self, command):
        expect_error("human_only", in_review(), command, ORCH)

    def test_plan_cannot_be_validated_before_one_is_proposed(self):
        state = run(TaskState(TaskType.FEATURE), (Command.PRIORITIZE, PO))
        expect_error("no_pending_plan", state, Command.VALIDATE_PLAN, PO)

    def test_rejected_plan_needs_a_new_version(self):
        state = run(
            TaskState(TaskType.FEATURE),
            (Command.PRIORITIZE, PO),
            (Command.PROPOSE_PLAN, ARCHI),
            (Command.REQUEST_PLAN_CHANGES, PO),
        )
        assert state.status is TaskStatus.TODO
        expect_error("no_pending_plan", state, Command.VALIDATE_PLAN, PO)
        state = run(state, (Command.PROPOSE_PLAN, ARCHI), (Command.VALIDATE_PLAN, PO))
        assert state.validated_plan_version == 2

    def test_only_po_decides(self):
        expect_error("forbidden", TaskState(TaskType.FEATURE), Command.PRIORITIZE, ADMIN)
        expect_error("forbidden", in_review(), Command.VALIDATE_RESULT, TESTEUR)

    def test_only_tester_confirms_a_fix(self):
        expect_error("forbidden", in_review(TaskType.BUGFIX), Command.CONFIRM_FIX, PO)

    def test_feature_has_no_tester_confirmation(self):
        expect_error("not_a_bugfix", in_review(), Command.CONFIRM_FIX, TESTEUR)

    def test_rejection_requires_comment_and_returns_to_in_progress(self):
        expect_error("comment_required", in_review(), Command.REJECT_RESULT, PO, comment="  ")
        state = run(in_review(), (Command.REJECT_RESULT, PO))
        assert state.status is TaskStatus.IN_PROGRESS
        assert not state.awaiting_human

    def test_done_is_final(self):
        done = run(in_review(), (Command.VALIDATE_RESULT, PO))
        expect_error("task_done", done, Command.REJECT_RESULT, PO)

    def test_status_cannot_be_skipped(self):
        expect_error("invalid_status", TaskState(TaskType.FEATURE), Command.SUBMIT_FOR_REVIEW, ORCH)
        expect_error("invalid_status", in_progress(), Command.VALIDATE_RESULT, PO)


class TestAwaitingHuman:
    def test_question_keeps_task_in_progress_and_blocks_review(self):
        state = run(in_progress(), (Command.ASK_HUMAN, ARCHI))
        assert state.status is TaskStatus.IN_PROGRESS
        assert state.awaiting_human and state.awaiting_reason is AwaitingReason.QUESTION
        expect_error("awaiting_human", state, Command.SUBMIT_FOR_REVIEW, ORCH)
        state = run(state, (Command.ANSWER_HUMAN, PO))
        assert not state.awaiting_human

    def test_deviation_from_validated_plan_stops_the_agent(self):
        state = run(in_progress(), (Command.PROPOSE_PLAN, ARCHI))
        assert state.awaiting_reason is AwaitingReason.PLAN_CHANGE
        expect_error("nothing_to_answer", state, Command.ANSWER_HUMAN, PO)
        state = run(state, (Command.VALIDATE_PLAN, PO))
        assert not state.awaiting_human
        assert state.validated_plan_version == 2

    def test_plan_cannot_be_revalidated_without_deviation(self):
        expect_error("no_pending_plan", in_progress(), Command.VALIDATE_PLAN, PO)

    def test_qa_loop_escalates_to_po_after_limit(self):
        state = in_progress(TaskType.BUGFIX)
        for _ in range(MAX_QA_ROUND_TRIPS - 1):
            state = run(state, (Command.RECORD_QA_FAILURE, ORCH))
            assert not state.awaiting_human
        state = run(state, (Command.RECORD_QA_FAILURE, ORCH))
        assert state.awaiting_reason is AwaitingReason.QA_LIMIT
        state = run(state, (Command.ANSWER_HUMAN, PO))
        assert state.qa_round_trips == 0

    def test_timeout_escalates_only_after_limit(self):
        state = in_progress()
        expect_error(
            "not_overdue",
            state,
            Command.ESCALATE_TIMEOUT,
            ORCH,
            now=NOW + MAX_TASK_EXECUTION - timedelta(seconds=1),
        )
        state = apply(state, Command.ESCALATE_TIMEOUT, ORCH, now=NOW + MAX_TASK_EXECUTION)
        assert state.awaiting_reason is AwaitingReason.TIMEOUT

    def test_only_orchestrator_moves_to_review(self):
        expect_error("forbidden", in_progress(), Command.SUBMIT_FOR_REVIEW, ARCHI)


class TestPendingDecision:
    def test_backlog_and_running_tasks_wait_for_nobody(self):
        assert pending_decision(TaskState(TaskType.FEATURE)) is None
        assert pending_decision(in_progress()) is None

    def test_proposed_plan_waits_for_po(self):
        state = run(TaskState(TaskType.FEATURE), (Command.PRIORITIZE, PO))
        assert pending_decision(state) is None
        state = run(state, (Command.PROPOSE_PLAN, ARCHI))
        assert pending_decision(state) is PendingDecision.PLAN
        state = run(state, (Command.REQUEST_PLAN_CHANGES, PO))
        assert pending_decision(state) is None

    def test_awaiting_reasons(self):
        assert pending_decision(run(in_progress(), (Command.ASK_HUMAN, ARCHI))) is PendingDecision.QUESTION
        assert pending_decision(run(in_progress(), (Command.PROPOSE_PLAN, ARCHI))) is PendingDecision.PLAN
        state = in_progress()
        for _ in range(MAX_QA_ROUND_TRIPS):
            state = run(state, (Command.RECORD_QA_FAILURE, ORCH))
        assert pending_decision(state) is PendingDecision.ESCALATION

    def test_review_waits_for_po_then_tester(self):
        state = in_review(TaskType.BUGFIX)
        assert pending_decision(state) is PendingDecision.RESULT
        state = run(state, (Command.VALIDATE_RESULT, PO))
        assert pending_decision(state) is PendingDecision.TESTER_CONFIRMATION
        assert pending_decision(run(state, (Command.CONFIRM_FIX, TESTEUR))) is None


DEBUG = Actor.agent(Casquette.DEBOGUEUR)


def free_text_bug() -> TaskState:
    return TaskState(TaskType.BUGFIX, report_required=True)


class TestNaturalLanguageBug:
    def test_reformulation_waits_for_its_author(self):
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG))
        assert state.report_version == 1
        assert pending_decision(state) is PendingDecision.REPORT

    def test_bug_cannot_be_prioritized_before_its_report_is_validated(self):
        expect_error("report_not_validated", free_text_bug(), Command.PRIORITIZE, PO)
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG))
        expect_error("report_not_validated", state, Command.PRIORITIZE, PO)

    def test_validated_report_unlocks_prioritization(self):
        state = run(
            free_text_bug(),
            (Command.PROPOSE_REPORT, DEBUG),
            (Command.VALIDATE_REPORT, TESTEUR),
            (Command.PRIORITIZE, PO),
        )
        assert state.status is TaskStatus.TODO
        assert state.validated_report_version == 1

    def test_author_can_have_the_reformulation_corrected(self):
        state = run(
            free_text_bug(), (Command.PROPOSE_REPORT, DEBUG), (Command.REQUEST_REPORT_CHANGES, TESTEUR)
        )
        assert pending_decision(state) is None
        expect_error("no_pending_report", state, Command.VALIDATE_REPORT, TESTEUR)
        state = run(state, (Command.PROPOSE_REPORT, DEBUG), (Command.VALIDATE_REPORT, TESTEUR))
        assert state.validated_report_version == 2

    def test_correction_requires_a_comment(self):
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG))
        expect_error("comment_required", state, Command.REQUEST_REPORT_CHANGES, TESTEUR, comment=" ")

    def test_po_can_validate_the_report_of_a_bug_they_wrote(self):
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG), (Command.VALIDATE_REPORT, PO))
        assert state.validated_report_version == 1

    def test_only_humans_validate_a_report(self):
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG))
        expect_error("human_only", state, Command.VALIDATE_REPORT, DEBUG)
        expect_error("forbidden", state, Command.VALIDATE_REPORT, ADMIN)

    def test_structured_bug_needs_no_reformulation(self):
        expect_error("no_report_needed", TaskState(TaskType.BUGFIX), Command.PROPOSE_REPORT, DEBUG)
        assert run(TaskState(TaskType.BUGFIX), (Command.PRIORITIZE, PO)).status is TaskStatus.TODO

    def test_validated_report_is_final(self):
        state = run(free_text_bug(), (Command.PROPOSE_REPORT, DEBUG), (Command.VALIDATE_REPORT, TESTEUR))
        expect_error("report_validated", state, Command.PROPOSE_REPORT, DEBUG)

    def test_reformulation_happens_in_backlog(self):
        state = run(
            free_text_bug(),
            (Command.PROPOSE_REPORT, DEBUG),
            (Command.VALIDATE_REPORT, TESTEUR),
            (Command.PRIORITIZE, PO),
        )
        expect_error("invalid_status", state, Command.PROPOSE_REPORT, DEBUG)
