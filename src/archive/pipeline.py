from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .models import AgentProposal, SourceItem


class SourceAdapter(Protocol):
    """Reads one public source and yields immutable source records."""

    source_id: str

    def discover(self) -> Iterable[str]: ...

    def fetch_item(self, source_item_id: str) -> SourceItem: ...


class EnrichmentAgent(Protocol):
    """Produces proposals. It never marks its own output as verified."""

    name: str
    version: str

    def enrich(self, item: SourceItem) -> Iterable[AgentProposal]: ...


@dataclass(slots=True)
class PipelineResult:
    source_item: SourceItem
    proposals: list[AgentProposal]


def process_item(
    adapter: SourceAdapter,
    source_item_id: str,
    agents: Iterable[EnrichmentAgent],
) -> PipelineResult:
    item = adapter.fetch_item(source_item_id)
    proposals: list[AgentProposal] = []

    for agent in agents:
        proposals.extend(agent.enrich(item))

    return PipelineResult(source_item=item, proposals=proposals)
