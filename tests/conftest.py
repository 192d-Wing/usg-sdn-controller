"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from usg_sdn.models.intent import IntentDocument
from usg_sdn.models.inventory import Device, DeviceCredential, Vendor

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_INTENT = ROOT / "examples" / "campus-fabric.yaml"
EXAMPLE_3TIER = ROOT / "examples" / "campus-fabric-3tier.yaml"


@pytest.fixture
def intent() -> IntentDocument:
    return IntentDocument.model_validate(yaml.safe_load(EXAMPLE_INTENT.read_text()))


@pytest.fixture
def intent_3tier() -> IntentDocument:
    return IntentDocument.model_validate(yaml.safe_load(EXAMPLE_3TIER.read_text()))


def _device(name: str, vendor: Vendor) -> Device:
    return Device(
        name=name,
        vendor=vendor,
        mgmt_address="fd00:face:b00c:ffff::1",
        credential=DeviceCredential(username="sdn"),
    )


@pytest.fixture
def junos_device() -> Device:
    return _device("leaf1", Vendor.JUNOS)


@pytest.fixture
def nxos_device() -> Device:
    return _device("spine2", Vendor.NXOS)


@pytest.fixture
def iosxe_device() -> Device:
    return _device("border1", Vendor.IOSXE)


@pytest.fixture
def eos_device() -> Device:
    return _device("spine1", Vendor.EOS)


@pytest.fixture
def aoscx_device() -> Device:
    return _device("leaf2", Vendor.AOSCX)
