"""Protocol checks: the test split is locked, and only the evaluation modules may open it."""
import re
from pathlib import Path

import pytest

from englishnet.data import TestSetLocked, load
from englishnet.propose import assert_train_only

PKG = Path(__file__).resolve().parent.parent / "englishnet"


def test_test_split_locked():
    with pytest.raises(TestSetLocked):
        load("test")
    with pytest.raises(TestSetLocked):
        load(["train", "test"])


def test_default_load_has_no_test_rows():
    assert all(r["split"] in ("train", "dev") for r in load())


def test_only_eval_modules_open_test():
    allowed = {"eval.py", "baselines.py", "patch.py", "finetune.py", "export_web.py"}  # report-only modules
    for f in PKG.glob("*.py"):
        if re.search(r"allow_test\s*=\s*True", f.read_text()) and f.name not in allowed and f.name != "data.py":
            pytest.fail(f"{f.name} opens the test split")


def test_prompts_take_train_rows_only():
    assert_train_only([{"id": "x", "split": "train"}])
    with pytest.raises(AssertionError):
        assert_train_only([{"id": "x", "split": "dev"}])


def test_heldout_sources_never_in_train_or_dev():
    assert not [r for r in load() if r["source"] in ("deepset", "notinject", "gandalf")]


def test_fresh_test_locked():
    from englishnet.fresh import FRESH, load_fresh
    if not FRESH.exists():
        pytest.skip("fresh set not built")
    with pytest.raises(TestSetLocked):
        load_fresh("fresh_test")
    assert all(r["split"] == "fresh_dev" for r in load_fresh("fresh_dev"))


def test_training_modules_never_open_fresh_test():
    for f in ("train.py", "propose.py", "adversary.py", "fit.py"):
        assert not re.search(r"\bload_fresh\b|englishnet\.fresh|from \.fresh", (PKG / f).read_text()), f


def test_logit_input_matches_forward():
    import math
    from englishnet.fit import feature
    assert feature(0.5, "logit") == 0.0
    assert abs(feature(0.9, "logit") - math.log(9)) < 1e-9
    assert feature(0.3) == 0.3
