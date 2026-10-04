# Bellhaven Sync

Keeps the CRM's Bellhaven Senior Living ownership picture in line with the operator's website. Each run scrapes the website, matches every community to CRM accounts, and queues proposed changes. A reviewer approves or rejects each one in a small web app. Nothing is written to the CRM without approval.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # add your CRM token
.venv/bin/python pipeline.py  # scrape, match, queue proposals
.venv/bin/python app.py       # review app on http://localhost:5050
.venv/bin/python -m pytest -q tests
```

## How it works

| File | Role |
|---|---|
| `scraper.py` | Collects every `/communities/<slug>` link from the home page and the paginated directory, then reads each detail page: name, address, city, state, zip, care offerings, administrator. The home page matters: it announces a 35th community (Findlay) that is missing from the directory. |
| `crm.py` | Thin client for the CRM API, with pagination. |
| `normalize.py` | Address keys that ignore abbreviations (W/West, St/Street, Pk/Pike), name keys, name similarity, and the mapping from website offerings to CRM `care_type`. |
| `matcher.py` | Matching and classification rules. Builds the proposals. |
| `apply.py` | Writes an approved proposal through the API. Enforces the billing SOP again at write time. |
| `store.py` | SQLite store for proposals, decisions and runs. |
| `pipeline.py` | The daily entry point. |
| `app.py`, `templates/` | The review app. |

### Matching

1. Candidates for a website community are all non-parent CRM accounts, under any parent or none, whose normalized street, city and state are equal. If there are none, the fallback is an account in the same city whose name similarity is 0.80 or higher. That fallback catches Ashtabula, whose CRM address is a PO Box.
2. If no candidate is found, the proposal is to **create** a new account under Bellhaven. Same-city accounts at other addresses are listed as evidence but are not matched. For example, Union Square Senior Living at 240 Market St is a different facility from Bellhaven at Union Square at 118 Union Square Dr.
3. If several candidates are found, they are copies of one facility. One **survivor** is chosen by, in order:
   - billing history,
   - already under Bellhaven,
   - the website administrator is a contact on the account,
   - Active status,
   - exact street,
   - name similarity.

   Every other copy is marked **duplicate**: `duplicate_of_account` is set to the survivor and the status becomes Inactive.
4. The survivor gets one proposal with every field that differs from the website:
   - name, street, city, state or zip;
   - `care_type`, only when the CRM value is not among the website's offerings;
   - status back to Active, if needed;
   - `parent_id` when it is not Bellhaven, which makes it a **re-parent** proposal.
5. **Billing SOP.** An account that has to leave its parent and has `lifetime_revenue > 0` and `outstanding_ar > 0` is never re-parented. It is left untouched, and its `chow_current_account` points to the current account for the facility. That is an existing account if one already sits under the right parent, or else a new account created in the same approval (Tiffin, Marietta, Sandusky). With revenue but no AR, the account is re-parented directly (Lima, Findlay). `apply.py` re-reads the account before any parent change and refuses it if billing is open, so a bad proposal cannot slip through.
6. Accounts under Bellhaven that are not on the website:
   - If another account sits at the same address under a different parent, the facility was sold. Sandusky is now under Millstone and has open AR, so it is a CHOW link.
   - Otherwise the account goes to **Needs Review** with a note, not Inactive, because the website alone does not tell whether the facility was sold or closed (Alliance, Coldwater).

### Safe reruns

Each proposal has a key: a hash of its type, account, location and the exact API calls it would make. The store inserts with `INSERT OR IGNORE`, so a proposal that was approved, rejected or is still pending is never queued twice. Approved changes also remove themselves at the source: the next run finds the CRM already correct, and accounts with `duplicate_of_account` or `chow_current_account` set are treated as resolved. If the CRM changes and a different fix becomes necessary, the key changes and the new proposal shows up. Pending proposals that a later run no longer produces are marked superseded. Creating an account first looks for one this tool already created at the same address, so a crash between the create and the status update cannot produce a second copy.

### Schedule

- `schedule/crontab` runs the pipeline at 9:00 on weekdays on the machine that hosts the review app, which shares the same SQLite file.
- `.github/workflows/daily.yml` is the hosted alternative. It runs the same pipeline and commits the decision store back to the repository. In production the store would live in a shared database instead.
- The pipeline only proposes changes. Writes happen when a reviewer approves.
