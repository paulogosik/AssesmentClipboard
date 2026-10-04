import hashlib
import json

import config
from normalize import address_key, crm_care_types, is_po_box, name_key, name_similarity, street_key

NEW_ACCOUNT_REF = "$new"


def is_parent_account(account):
    return "(Parent Account)" in account["name"]


def is_resolved(account):
    return bool(account["duplicate_of_account"] or account["chow_current_account"])


def requires_chow(account):
    return account["lifetime_revenue"] > 0 and account["outstanding_ar"] > 0


def money(value):
    return f"${value:,.0f}"


def describe(account):
    return (
        f"{account['name']} [{account['account_id']}] · {account['billing_street']}, {account['billing_city']} "
        f"{account['billing_state']} {account['billing_zip']} · parent: {account['parent_name'] or '(none)'} · "
        f"status: {account['status']}"
    )


def billing_evidence(account):
    rule = "CHOW required (keep old account, link to current one)" if requires_chow(account) else "re-parent directly"
    return (
        f"Billing on {account['name']}: lifetime_revenue {money(account['lifetime_revenue'])}, "
        f"outstanding_ar {money(account['outstanding_ar'])} → SOP: {rule}"
    )


def append_note(account, text):
    existing = (account.get("note") or "").strip()
    if text in existing:
        return existing
    return f"{existing} | {text}" if existing else text


def proposal_key(proposal):
    identity = {k: proposal[k] for k in ("type", "account_id", "location_slug", "actions")}
    return hashlib.sha1(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def make_proposal(kind, title, actions, evidence, account=None, location=None, diff=None):
    proposal = {
        "type": kind,
        "title": title,
        "account_id": account["account_id"] if account else "",
        "account_name": account["name"] if account else "",
        "location_slug": location["slug"] if location else "",
        "actions": actions,
        "evidence": evidence,
        "diff": diff or [],
    }
    proposal["key"] = proposal_key(proposal)
    return proposal


class Matcher:
    def __init__(self, locations, accounts, contacts):
        self.locations = locations
        self.parent = next(a for a in accounts if a["name"] == config.OPERATOR_PARENT_NAME)
        self.facilities = [a for a in accounts if not is_parent_account(a) and not is_resolved(a)]
        self.contacts_by_account = {}
        for contact in contacts:
            if contact.get("is_active", True):
                self.contacts_by_account.setdefault(contact["account_id"], []).append(contact)
        self.proposals = []
        self.confirmed = []
        self.used_account_ids = set()

    def under_operator(self, account):
        return account["parent_id"] == self.parent["account_id"]

    def admin_contact(self, location, account):
        target = name_key(location["administrator"])
        for contact in self.contacts_by_account.get(account["account_id"], []):
            if target and name_key(contact["name"]) == target:
                return contact
        return None

    def candidates(self, location):
        key = address_key(location["street"], location["city"], location["state"])
        by_address = [a for a in self.facilities if address_key(a["billing_street"], a["billing_city"], a["billing_state"]) == key]
        if by_address:
            return by_address, "address"
        same_city = [
            a for a in self.facilities
            if a["billing_state"] == location["state"] and name_key(a["billing_city"]) == name_key(location["city"])
        ]
        by_name = [a for a in same_city if name_similarity(a["name"], location["name"]) >= config.NAME_MATCH_THRESHOLD]
        return by_name, "name"

    def survivor_rank(self, location, account):
        return (
            account["lifetime_revenue"] > 0,
            self.under_operator(account),
            self.admin_contact(location, account) is not None,
            account["status"] == "Active",
            account["billing_street"].strip().lower() == location["street"].strip().lower(),
            name_similarity(account["name"], location["name"]),
        )

    def location_evidence(self, location, account, matched_by):
        evidence = [
            f"Website: {location['name']} · {location['street']}, {location['city']} {location['state']} "
            f"{location['zip']} · {', '.join(location['care_offerings'])} · {location['url']}"
        ]
        if account:
            evidence.append(f"CRM: {describe(account)}")
            if matched_by == "address":
                evidence.append(f"Address match: '{account['billing_street']}' and '{location['street']}' normalize to the same street")
            else:
                evidence.append(
                    f"Matched by name in the same city (similarity {name_similarity(account['name'], location['name'])}); "
                    f"CRM street '{account['billing_street']}' differs from the website"
                )
            evidence.append(f"Name similarity CRM vs website: {name_similarity(account['name'], location['name'])}")
            contact = self.admin_contact(location, account)
            if contact:
                evidence.append(f"Website administrator '{location['administrator']}' is a contact on this account ({contact['title']})")
            else:
                evidence.append(f"Website administrator '{location['administrator']}' not found among this account's contacts")
        return evidence

    def field_changes(self, location, account):
        changes = {}
        if name_key(account["name"]) != name_key(location["name"]):
            changes["name"] = location["name"]
        if street_key(account["billing_street"]) != street_key(location["street"]) or is_po_box(account["billing_street"]):
            changes["billing_street"] = location["street"]
        if name_key(account["billing_city"]) != name_key(location["city"]):
            changes["billing_city"] = location["city"]
        if account["billing_state"] != location["state"]:
            changes["billing_state"] = location["state"]
        if account["billing_zip"] != location["zip"]:
            changes["billing_zip"] = location["zip"]
        site_types = crm_care_types(location["care_offerings"])
        if site_types and account["care_type"] not in site_types:
            changes["care_type"] = site_types[0]
        if account["status"] != "Active":
            changes["status"] = "Active"
        return changes

    def new_account_fields(self, location, note):
        site_types = crm_care_types(location["care_offerings"])
        return {
            "name": location["name"],
            "parent_id": self.parent["account_id"],
            "billing_street": location["street"],
            "billing_city": location["city"],
            "billing_state": location["state"],
            "billing_zip": location["zip"],
            "care_type": site_types[0] if site_types else "",
            "status": "Active",
            "note": note,
        }

    def diff(self, account, fields):
        return [{"field": f, "before": account.get(f, ""), "after": v} for f, v in fields.items() if f != "note"]

    def match_location(self, location):
        found, matched_by = self.candidates(location)
        self.used_account_ids.update(a["account_id"] for a in found)
        if not found:
            self.propose_create(location)
            return
        locked = [a for a in found if requires_chow(a) and not self.under_operator(a)]
        free = [a for a in found if a not in locked]
        survivor = max(free, key=lambda a: self.survivor_rank(location, a)) if free else None
        if survivor:
            self.propose_survivor_fix(location, survivor, matched_by)
        if locked:
            self.propose_chow(location, locked, survivor, matched_by)
        for loser in free:
            if loser is not survivor:
                self.propose_duplicate(location, loser, survivor, found)

    def propose_survivor_fix(self, location, account, matched_by):
        changes = self.field_changes(location, account)
        evidence = self.location_evidence(location, account, matched_by)
        reparent = not self.under_operator(account)
        if reparent:
            changes["parent_id"] = self.parent["account_id"]
            changes["note"] = append_note(
                account,
                f"Re-parented to {config.OPERATOR_NAME}: listed on the operator website ({location['slug']}); "
                f"previous parent: {account['parent_name'] or 'none'}",
            )
            evidence.append(billing_evidence(account))
        if not changes:
            self.confirmed.append({"location": location, "account": account})
            return
        kind = "reparent" if reparent else "update"
        title = (
            f"Re-parent {account['name']} to {config.OPERATOR_NAME}" if reparent
            else f"Update {account['name']}: {', '.join(changes)}"
        )
        self.proposals.append(make_proposal(
            kind, title, [{"op": "patch", "account_id": account["account_id"], "fields": changes}],
            evidence, account, location, self.diff(account, changes),
        ))

    def propose_chow(self, location, locked, survivor, matched_by):
        actions, evidence = [], []
        target = survivor["account_id"] if survivor else NEW_ACCOUNT_REF
        if not survivor:
            note = f"Created by bellhaven-sync for {location['slug']}: change of ownership from " + ", ".join(
                a["account_id"] for a in locked
            )
            actions.append({"op": "create", "fields": self.new_account_fields(location, note)})
        for account in locked:
            evidence += self.location_evidence(location, account, matched_by)
            evidence.append(billing_evidence(account))
            actions.append({"op": "patch", "account_id": account["account_id"], "fields": {"chow_current_account": target}})
        target_text = f"existing account {survivor['name']} [{survivor['account_id']}]" if survivor else "a new account under the operator"
        title = f"CHOW: keep {', '.join(a['name'] for a in locked)} as is and link it to {target_text}"
        self.proposals.append(make_proposal(
            "chow", title, actions, evidence, locked[0], location,
            [{"field": "chow_current_account", "before": a["chow_current_account"], "after": target} for a in locked],
        ))

    def propose_duplicate(self, location, loser, survivor, group):
        fields = {
            "duplicate_of_account": survivor["account_id"],
            "status": "Inactive",
            "note": append_note(loser, f"Duplicate of {survivor['account_id']} ({location['name']}): same facility address"),
        }
        evidence = [
            f"{len(group)} CRM accounts point to the website location {location['name']} ({location['street']}, {location['city']})",
            f"Losing copy: {describe(loser)}",
            f"Surviving account: {describe(survivor)}",
            "Survivor chosen by: billing history, then operator parent, then administrator contact, then active status, then exact address, then name similarity",
            billing_evidence(loser),
        ]
        self.proposals.append(make_proposal(
            "duplicate", f"Mark {loser['name']} as duplicate of {survivor['name']}",
            [{"op": "patch", "account_id": loser["account_id"], "fields": fields}],
            evidence, loser, location, self.diff(loser, fields),
        ))

    def propose_create(self, location):
        fields = self.new_account_fields(location, f"Created by bellhaven-sync from the operator website ({location['slug']})")
        evidence = self.location_evidence(location, None, None)
        evidence.append("No CRM account shares this address, and no account in the same city has a similar name")
        nearby = [a for a in self.facilities if a["billing_state"] == location["state"] and name_key(a["billing_city"]) == name_key(location["city"])]
        for account in nearby:
            evidence.append(f"Same-city account NOT matched (different address): {describe(account)}")
        self.proposals.append(make_proposal(
            "create", f"Create account for {location['name']} ({location['city']}, {location['state']})",
            [{"op": "create", "fields": fields}], evidence, None, location,
            [{"field": f, "before": "", "after": v} for f, v in fields.items() if f != "note"],
        ))

    def handle_missing_from_site(self):
        for account in self.facilities:
            if not self.under_operator(account) or account["account_id"] in self.used_account_ids:
                continue
            if account["status"] == "Inactive":
                continue
            key = address_key(account["billing_street"], account["billing_city"], account["billing_state"])
            twins = [
                a for a in self.facilities
                if a is not account and not self.under_operator(a)
                and address_key(a["billing_street"], a["billing_city"], a["billing_state"]) == key
            ]
            evidence = [
                f"CRM: {describe(account)}",
                f"Not listed among the {len(self.locations)} communities on the {config.OPERATOR_NAME} website",
                billing_evidence(account),
            ]
            if twins:
                new_owner = max(twins, key=lambda a: (a["status"] == "Active", a["lifetime_revenue"]))
                evidence.append(f"Another account at the same address under a different parent: {describe(new_owner)}")
                if requires_chow(account):
                    fields = {"chow_current_account": new_owner["account_id"]}
                    kind, title = "chow", f"CHOW: keep {account['name']} as is and link it to {new_owner['name']} ({new_owner['parent_name']})"
                else:
                    fields = {
                        "duplicate_of_account": new_owner["account_id"],
                        "status": "Inactive",
                        "note": append_note(account, f"No longer on the {config.OPERATOR_NAME} website; facility now tracked as {new_owner['account_id']}"),
                    }
                    kind, title = "duplicate", f"Mark {account['name']} as duplicate of {new_owner['name']}"
            else:
                if account["status"] == "Needs Review":
                    continue
                fields = {
                    "status": "Needs Review",
                    "note": append_note(account, f"Not listed on the {config.OPERATOR_NAME} website; confirm whether it was sold or closed"),
                }
                kind, title = "not_on_site", f"Flag {account['name']} for review: no longer on the website"
                evidence.append("No other CRM account at this address, so the new owner is unknown; status set to Needs Review instead of Inactive")
            self.proposals.append(make_proposal(
                kind, title, [{"op": "patch", "account_id": account["account_id"], "fields": fields}],
                evidence, account, None, self.diff(account, fields),
            ))

    def run(self):
        for location in self.locations:
            self.match_location(location)
        self.handle_missing_from_site()
        return self.proposals, self.confirmed
