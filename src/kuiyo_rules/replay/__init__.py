"""Pure replay contracts for deterministic rule execution."""

from kuiyo_rules.replay.contracts import (
    ParityStatus,
    ReplayDayPlan,
    ReplayDayResult,
    ReplayPlan,
    ReplayProgress,
    ReplayRequest,
    ReplayResult,
    ReplayStageAttempt,
    ReplayStageInputPlan,
    ReplayStageResult,
    ResolvedReplayDataset,
    ResolvedReplayStageData,
    RuleStageOutput,
)
from kuiyo_rules.replay.engine import (
    ReplayEvaluatorError,
    ReplayInputError,
    apply_input_conformance,
    build_replay_plan,
    execute_replay_stage,
    finalize_replay_day,
    prepare_next_stage,
)
from kuiyo_rules.replay.opening_candidate import OPENING_CANDIDATE_REPLAY_POLICY
from kuiyo_rules.replay.registry import ReplayPolicyRegistry, RuleReplayPolicy

DEFAULT_REPLAY_POLICIES = ReplayPolicyRegistry((OPENING_CANDIDATE_REPLAY_POLICY,))

__all__ = [
    "ParityStatus",
    "ReplayDayPlan",
    "ReplayDayResult",
    "ReplayPlan",
    "ReplayProgress",
    "ReplayRequest",
    "ReplayResult",
    "ReplayStageAttempt",
    "ReplayStageInputPlan",
    "ReplayStageResult",
    "ResolvedReplayDataset",
    "ResolvedReplayStageData",
    "RuleStageOutput",
    "ReplayEvaluatorError",
    "ReplayInputError",
    "ReplayPolicyRegistry",
    "RuleReplayPolicy",
    "OPENING_CANDIDATE_REPLAY_POLICY",
    "DEFAULT_REPLAY_POLICIES",
    "apply_input_conformance",
    "build_replay_plan",
    "execute_replay_stage",
    "finalize_replay_day",
    "prepare_next_stage",
]
