"""Intent model validation tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from usg_sdn.models.intent import Fabric, IntentDocument, Node, NodeRole


def test_intent_round_trip(intent: IntentDocument) -> None:
    dumped = intent.model_dump(mode="json", by_alias=True)
    again = IntentDocument.model_validate(dumped)
    assert again == intent


def test_duplicate_node_names_rejected() -> None:
    with pytest.raises(ValidationError):
        Fabric(
            name="x",
            nodes=[
                Node(
                    name="a",
                    role=NodeRole.LEAF,
                    inventory_ref="a",
                    loopback_v6="fd00::1",
                    isis_net="49.0001.0000.0000.0001.00",
                    asn=65001,
                ),
                Node(
                    name="a",
                    role=NodeRole.LEAF,
                    inventory_ref="a",
                    loopback_v6="fd00::2",
                    isis_net="49.0001.0000.0000.0002.00",
                    asn=65002,
                ),
            ],
            links=[],
        )


def test_invalid_isis_net() -> None:
    with pytest.raises(ValidationError):
        Node(
            name="a",
            role=NodeRole.LEAF,
            inventory_ref="a",
            loopback_v6="fd00::1",
            isis_net="not-a-net",
            asn=65001,
        )
