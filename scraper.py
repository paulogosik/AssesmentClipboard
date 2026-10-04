import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config


def _get(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def community_links(soup):
    return [urljoin(config.SITE_BASE_URL, a["href"]) for a in soup.select('a[href^="/communities/"]')]


def list_community_urls():
    urls = community_links(_get(urljoin(config.SITE_BASE_URL, "/")))
    page_url = urljoin(config.SITE_BASE_URL, "/communities")
    while page_url:
        soup = _get(page_url)
        urls.extend(community_links(soup))
        next_link = soup.find("a", string=re.compile("Next"))
        page_url = urljoin(config.SITE_BASE_URL, next_link["href"]) if next_link else None
    return list(dict.fromkeys(urls))


def parse_city_line(line):
    match = re.match(r"^(.*),\s*([A-Z]{2})\s+(\d{5})", line.strip())
    if not match:
        return line.strip(), "", ""
    return match.group(1).strip(), match.group(2), match.group(3)


def scrape_community(url):
    soup = _get(url)
    fields = {}
    for dt in soup.select("dl.detail dt, .detail dt"):
        dd = dt.find_next_sibling("dd")
        fields[dt.get_text(strip=True).lower()] = dd
    address_lines = [line.strip() for line in fields["address"].get_text("\n").split("\n") if line.strip()]
    city, state, zip_code = parse_city_line(address_lines[-1])
    offerings_dd = fields.get("care offerings")
    offerings = [li.get_text(strip=True) for li in offerings_dd.find_all(["li", "span"])] if offerings_dd else []
    if offerings_dd and not offerings:
        offerings = [part.strip() for part in offerings_dd.get_text("\n").split("\n") if part.strip()]
    return {
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "url": url,
        "name": soup.find("h1").get_text(strip=True),
        "street": " ".join(address_lines[:-1]),
        "city": city,
        "state": state,
        "zip": zip_code,
        "care_offerings": offerings,
        "administrator": fields["administrator"].get_text(strip=True) if "administrator" in fields else "",
        "phone": fields["phone"].get_text(strip=True) if "phone" in fields else "",
    }


def scrape_all():
    return [scrape_community(url) for url in list_community_urls()]


if __name__ == "__main__":
    locations = scrape_all()
    config.LOCATIONS_PATH.parent.mkdir(exist_ok=True)
    config.LOCATIONS_PATH.write_text(json.dumps(locations, indent=2))
    print(f"{len(locations)} locations saved to {config.LOCATIONS_PATH}")
