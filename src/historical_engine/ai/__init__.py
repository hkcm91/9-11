"""AI provider interfaces and the assisted-decision pipeline.

Boundary, stated once: AI assists with organisation and inference. It proposes.
A human reviews. Nothing in this package can mark anything verified.
"""

from historical_engine.ai.batch import (
    load_decision_requests,
    request_from_dict,
    run_decision_batch,
    write_decision_batch,
)
from historical_engine.ai.fakes import (
    FakeDecisionProvider,
    FakeEmbeddingProvider,
    FakeGenerativeProvider,
    FakeTranscriptionProvider,
    FakeVisionProvider,
)
from historical_engine.ai.jev import JevDecisionProvider, JevTransport
from historical_engine.ai.pipeline import AssistedDecision, run_decision
from historical_engine.ai.providers import (
    AiProposalError,
    AiProviderError,
    DecisionProvider,
    EmbeddingProvider,
    GenerativeProvider,
    ProviderRegistry,
    TranscriptionProvider,
    VisionProvider,
    proposal_from_decision,
    validate_decision,
)
from historical_engine.ai.questions import (
    ANSWER_SPACE,
    PROPOSAL_TYPE_FOR_QUESTION,
    DecisionQuestion,
    DecisionRequest,
    DecisionResponse,
)

__all__ = [
    "ANSWER_SPACE",
    "AiProposalError",
    "AiProviderError",
    "AssistedDecision",
    "DecisionProvider",
    "DecisionQuestion",
    "DecisionRequest",
    "DecisionResponse",
    "EmbeddingProvider",
    "FakeDecisionProvider",
    "FakeEmbeddingProvider",
    "FakeGenerativeProvider",
    "FakeTranscriptionProvider",
    "FakeVisionProvider",
    "GenerativeProvider",
    "JevDecisionProvider",
    "JevTransport",
    "load_decision_requests",
    "request_from_dict",
    "run_decision_batch",
    "PROPOSAL_TYPE_FOR_QUESTION",
    "ProviderRegistry",
    "TranscriptionProvider",
    "VisionProvider",
    "proposal_from_decision",
    "run_decision",
    "validate_decision",
    "write_decision_batch",
]
