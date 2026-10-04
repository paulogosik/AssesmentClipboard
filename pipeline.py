import json
from collections import Counter

import config
import store
from crm import CRM
from matcher import Matcher
from scraper import scrape_all


def run():
    locations = scrape_all()
    config.LOCATIONS_PATH.parent.mkdir(exist_ok=True)
    config.LOCATIONS_PATH.write_text(json.dumps(locations, indent=2))
    crm = CRM()
    proposals, confirmed = Matcher(locations, crm.list_accounts(), crm.list_contacts()).run()
    conn = store.connect()
    new = store.save_proposals(conn, proposals)
    store.record_run(conn, len(locations), len(proposals), new, len(confirmed))
    by_type = Counter(p["type"] for p in proposals)
    print(f"Scraped {len(locations)} locations; {len(confirmed)} confirmed matches with nothing to change")
    print(f"{len(proposals)} proposals this run ({dict(by_type)}); {new} new, {len(proposals) - new} already in the queue or decided")
    return new


if __name__ == "__main__":
    run()
