from matcher import NEW_ACCOUNT_REF, requires_chow
from normalize import address_key


class SOPViolation(Exception):
    pass


def unwrap(body):
    return body.get("data", body) if isinstance(body, dict) else body


def find_previously_created(crm, fields):
    key = address_key(fields["billing_street"], fields["billing_city"], fields["billing_state"])
    for account in crm.list_accounts(zip=fields["billing_zip"]):
        same_place = address_key(account["billing_street"], account["billing_city"], account["billing_state"]) == key
        if account.get("created_by_candidate") and same_place and account["parent_id"] == fields["parent_id"]:
            return account
    return None


def apply_proposal(crm, proposal):
    log = []
    new_account_id = None
    for action in proposal["actions"]:
        if action["op"] == "create":
            existing = find_previously_created(crm, action["fields"])
            account = existing or unwrap(crm.create_account(action["fields"]))
            new_account_id = account["account_id"]
            log.append({"op": "create", "account_id": new_account_id, "reused_existing": bool(existing)})
            continue
        fields = {k: (new_account_id if v == NEW_ACCOUNT_REF else v) for k, v in action["fields"].items()}
        if "parent_id" in fields:
            current = unwrap(crm.get_account(action["account_id"]))
            if current["parent_id"] != fields["parent_id"] and requires_chow(current):
                raise SOPViolation(
                    f"{current['name']} has revenue and outstanding AR; billing SOP forbids changing its parent"
                )
        crm.update_account(action["account_id"], fields)
        log.append({"op": "patch", "account_id": action["account_id"], "fields": sorted(fields)})
    return log
