import requests

import config


class CRM:
    def __init__(self, base_url=config.CRM_BASE_URL, token=config.CRM_API_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _request(self, method, path, **kwargs):
        response = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def _list_all(self, path, **params):
        rows, page = [], 1
        while True:
            body = self._request("GET", path, params={**params, "page": page, "page_size": 50})
            rows.extend(body["data"])
            if len(rows) >= body["total"] or not body["data"]:
                return rows
            page += 1

    def list_accounts(self, **filters):
        return self._list_all("/accounts", **filters)

    def list_contacts(self, **filters):
        return self._list_all("/contacts", **filters)

    def get_account(self, account_id):
        return self._request("GET", f"/accounts/{account_id}")

    def update_account(self, account_id, fields):
        return self._request("PATCH", f"/accounts/{account_id}", json=fields)

    def create_account(self, fields):
        return self._request("POST", "/accounts", json=fields)
