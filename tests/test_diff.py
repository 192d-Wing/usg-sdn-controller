from __future__ import annotations

from usg_sdn.render import config_diff


def test_diff_empty_when_identical() -> None:
    assert config_diff("a\nb\n", "a\nb\n") == ""


def test_diff_detects_change() -> None:
    d = config_diff("a\nb\n", "a\nc\n")
    assert "-b" in d and "+c" in d
