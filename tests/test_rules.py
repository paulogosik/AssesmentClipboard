import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply import SOPViolation, apply_proposal
from matcher import Matcher, requires_chow
from normalize import address_key, crm_care_types

PARENT = {"account_id": "P1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": "", "parent_name": ""}
OTHER = {"account_id": "P2", "name": "Cedar Trail Communities (Parent Account)", "parent_id": "", "parent_name": ""}


def account(account_id, name, street, revenue=0, ar=0, parent=OTHER, status="Active"):
    return {
        "account_id": account_id, "name": name, "parent_id": parent["account_id"], "parent_name": parent["name"],
        "billing_street": street, "billing_city": "Tiffin", "billing_state": "OH", "billing_zip": "44883",
        "care_type": "Skilled Nursing", "status": status, "phone": "", "lifetime_revenue": revenue,
        "outstanding_ar": ar, "chow_current_account": "", "duplicate_of_account": "", "note": "",
    }


LOCATION = {
    "slug": "bellhaven-of-tiffin", "url": "x", "name": "Bellhaven of Tiffin", "street": "45 St Lawrence Dr",
    "city": "Tiffin", "state": "OH", "zip": "44883", "care_offerings": ["Short-Term Rehabilitation & Nursing"],
    "administrator": "Walt Osei", "phone": "",
}


def run(*accounts):
    return Matcher([LOCATION], [PARENT, OTHER, *accounts], []).run()[0]


def test_address_normalization_ignores_abbreviations():
    assert address_key("1120 W Main St", "Owosso", "MI") == address_key("1120 West Main Street", "Owosso", "MI")
    assert address_key("3313 Wilmington Pk", "Kettering", "OH") == address_key("3313 Wilmington Pike", "Kettering", "OH")


def test_care_offerings_map_to_crm_values():
    assert crm_care_types(["Short-Term Rehabilitation & Nursing", "Memory Support"]) == ["Skilled Nursing", "Memory Care"]


def test_revenue_and_ar_require_chow():
    proposals = run(account("A1", "Bellhaven of Tiffin", "45 St Lawrence Dr", revenue=84000, ar=12400))
    assert [p["type"] for p in proposals] == ["chow"]
    ops = [a["op"] for a in proposals[0]["actions"]]
    assert ops == ["create", "patch"]
    assert proposals[0]["actions"][1]["fields"] == {"chow_current_account": "$new"}


def test_revenue_without_ar_is_reparented_directly():
    proposals = run(account("A1", "Bellhaven of Tiffin", "45 St Lawrence Dr", revenue=47000, ar=0))
    assert [p["type"] for p in proposals] == ["reparent"]
    assert proposals[0]["actions"][0]["fields"]["parent_id"] == "P1"


def test_duplicates_keep_the_operator_account():
    proposals = run(
        account("A1", "Cedar Trail of Tiffin", "45 St Lawrence Drive"),
        account("A2", "Bellhaven of Tiffin", "45 St Lawrence Dr", parent=PARENT),
    )
    duplicate = next(p for p in proposals if p["type"] == "duplicate")
    assert duplicate["account_id"] == "A1"
    assert duplicate["actions"][0]["fields"]["duplicate_of_account"] == "A2"


def test_proposal_keys_are_stable_between_runs():
    a = account("A1", "Cedar Trail of Tiffin", "45 St Lawrence Dr")
    assert [p["key"] for p in run(dict(a))] == [p["key"] for p in run(dict(a))]


class FakeCRM:
    def __init__(self, current):
        self.current = current
        self.patched = []

    def get_account(self, account_id):
        return self.current

    def update_account(self, account_id, fields):
        self.patched.append((account_id, fields))


def test_apply_refuses_reparent_when_billing_is_open():
    crm = FakeCRM(account("A1", "Bellhaven of Tiffin", "45 St Lawrence Dr", revenue=10, ar=5))
    proposal = {"actions": [{"op": "patch", "account_id": "A1", "fields": {"parent_id": "P1"}}]}
    try:
        apply_proposal(crm, proposal)
        assert False
    except SOPViolation:
        assert crm.patched == []


def test_requires_chow_needs_both_revenue_and_ar():
    assert requires_chow({"lifetime_revenue": 1, "outstanding_ar": 1})
    assert not requires_chow({"lifetime_revenue": 1, "outstanding_ar": 0})
    assert not requires_chow({"lifetime_revenue": 0, "outstanding_ar": 1})
