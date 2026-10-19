from __future__ import annotations

import pytest

from taarr.evaluate import audit, score

def item(key, outcome, status="gold_verified", group="g", split=None):
    value={"benchmark_item_id":key,"gold_outcome":outcome,"annotation_status":status,"split_group_id":group}
    if split is not None: value["split"]=split
    return value

def pred(key,outcome): return {"benchmark_item_id":key,"outcome":outcome}

def test_empty_gold_is_unavailable_not_zero():
    result=score([item("draft","Applicable","draft")],[pred("draft","Applicable")])
    assert result["status"]=="unavailable" and result["accuracy"] is None

def test_four_way_metrics_and_draft_exclusion():
    rows=[item("1","Applicable"),item("2","Not applicable"),item("3","Conflict"),item("4","Indeterminate"),item("draft","Applicable","draft")]
    predictions=[pred("1","Applicable"),pred("2","Applicable"),pred("3","Conflict"),pred("4","Indeterminate"),pred("draft","Not applicable")]
    result=score(rows,predictions)
    assert result["matched_n"]==4
    assert result["accuracy"]==0.75
    assert result["confusion_matrix"]["Not applicable"]["Applicable"]==1
    assert result["prediction_ids_not_in_gold"]==["draft"]

def test_missing_predictions_report_coverage():
    result=score([item("1","Applicable"),item("2","Conflict")],[pred("1","Applicable")])
    assert result["coverage"]==0.5 and result["missing_prediction_ids"]==["2"]

def test_duplicate_predictions_rejected():
    with pytest.raises(ValueError,match="duplicate prediction"):
        score([item("1","Applicable")],[pred("1","Applicable"),pred("1","Conflict")])

def test_invalid_prediction_rejected():
    with pytest.raises(ValueError,match="invalid outcome"):
        score([item("1","Applicable")],[pred("1","Maybe")])

def test_audit_detects_group_leakage():
    result=audit([item("1","Applicable",group="same",split="train"),item("2","Conflict",group="same",split="test"),item("3","Applicable","draft")])
    assert result["gold_verified_n"]==2 and result["split_group_leakage"]==["same"]
