import os
import time
import hmac
import hashlib
import httpx
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class DomainResult:
    domain: str
    available: bool
    price: float
    currency: str


@dataclass
class DomainInfo:
    domain: str
    registered: bool
    expiration_date: str
    nameservers: List[str]


@dataclass
class PurchaseResult:
    success: bool
    order_id: str
    transaction_id: str
    domain: str
    error: Optional[str] = None


class NamecheapClient:
    def __init__(self):
        self.api_key = os.getenv("NAMECHEAP_API_KEY", "")
        self.api_user = os.getenv("NAMECHEAP_API_USER", "")
        self.ip = os.getenv("NAMECHEAP_IP", "")
        self.base_url = "https://api.namecheap.com/xml.response"
        self.client = httpx.AsyncClient(timeout=30.0)

    def _sign(self, command: str) -> str:
        if not self.api_key:
            return ""

        timestamp = str(int(time.time()))
        signature_base = f"{self.api_user}{self.api_key}{command}{self.ip}{timestamp}"
        return hmac.new(
            self.api_key.encode(), signature_base.encode(), hashlib.md5
        ).hexdigest()

    async def _request(self, command: str, params: Dict[str, str] = {}) -> Dict:
        default_params = {
            "ApiUser": self.api_user,
            "ApiKey": self.api_key,
            "UserName": self.api_user,
            "Command": command,
            "ClientIP": self.ip,
        }
        all_params = {**default_params, **params}

        signature = self._sign(command)
        if signature:
            all_params["ApiSig"] = signature

        response = await self.client.get(self.base_url, params=all_params)
        response.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)

        if root.find(".//Error") is not None:
            error = root.find(".//Error").text
            raise ValueError(f"Namecheap API error: {error}")

        return self._parse_response(root, command)

    def _parse_response(self, root, command: str) -> Dict:
        result = {"command": command, "success": True}

        if "domains.available" in command:
            result["domains"] = []
            for domain_check in root.findall(".//DomainCheck"):
                result["domains"].append({
                    "domain": domain_check.get("Domain"),
                    "available": domain_check.get("Available") == "true",
                })

        elif "domains.create" in command:
            result["success"] = True
            result["domain"] = root.find(".//Domain").text if root.find(".//Domain") is not None else ""

        return result

    async def check_availability(self, domains: List[str]) -> Dict[str, bool]:
        command = "namecheap.domains.check"
        domain_list = ",".join(domains)

        params = {"DomainList": domain_list}
        result = await self._request(command, params)

        availability = {}
        for item in result.get("domains", []):
            availability[item["domain"]] = item["available"]

        return availability

    async def search_domains(
        self, keyword: str, tlds: List[str] = None, max_results: int = 10
    ) -> List[DomainResult]:
        if not tlds:
            tlds = [".com", ".io", ".co"]

        domains = [f"{keyword}{tld}" for tld in tlds[:5]]
        availability = await self.check_availability(domains)

        results = []
        for domain, available in availability.items():
            price = 10.00 if available else 0
            results.append(DomainResult(
                domain=domain,
                available=available,
                price=price,
                currency="USD",
            ))

        return results[:max_results]

    async def purchase_domain(
        self, domain: str, years: int = 1, nameservers: List[str] = None
    ) -> PurchaseResult:
        try:
            command = "namecheap.domains.create"
            params = {
                "DomainName": domain,
                "Years": str(years),
                "RegistrantOrganizationName": "ChampMail",
                "RegistrantFirstName": "Champ",
                "RegistrantLastName": "Mail",
                "RegistrantEmail": "admin@champmail.com",
                "RegistrantPhone": "+1.5555555555",
                "RegistrantCity": "San Francisco",
                "RegistrantCountry": "US",
                "RegistrantPostalCode": "94105",
            }

            if nameservers:
                params["Nameservers"] = ",".join(nameservers[:5])

            result = await self._request(command, params)

            return PurchaseResult(
                success=True,
                order_id=result.get("order_id", ""),
                transaction_id=result.get("transaction_id", ""),
                domain=domain,
            )

        except Exception as e:
            return PurchaseResult(
                success=False,
                order_id="",
                transaction_id="",
                domain=domain,
                error=str(e),
            )

    async def get_domain_info(self, domain: str) -> DomainInfo:
        command = "namecheap.domains.getInfo"
        params = {"DomainName": domain}

        result = await self._request(command, params)

        return DomainInfo(
            domain=domain,
            registered=result.get("IsRegistered", True),
            expiration_date=result.get("Expires", ""),
            nameservers=result.get("Nameservers", []),
        )

    async def close(self):
        await self.client.aclose()


namecheap_client = NamecheapClient()