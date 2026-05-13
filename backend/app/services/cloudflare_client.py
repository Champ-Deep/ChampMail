import os
import httpx
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Zone:
    id: str
    name: str
    status: str
    plan: str


@dataclass
class DNSRecord:
    id: str
    type: str
    name: str
    content: str
    priority: int
    ttl: int
    proxied: bool


@dataclass
class DNSSetupResult:
    success: bool
    records: List[DNSRecord]
    error: Optional[str] = None


@dataclass
class PropagationStatus:
    mx: bool
    spf: bool
    dkim: bool
    dmarc: bool
    all_verified: bool


class CloudflareClient:
    def __init__(self):
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict:
        url = f"{self.base_url}{endpoint}"
        response = await self.client.request(
            method, url, json=data, headers=self.headers
        )
        response.raise_for_status()

        result = response.json()

        if not result.get("success", False):
            errors = result.get("errors", [])
            error_msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
            raise ValueError(f"Cloudflare API error: {error_msg}")

        return result.get("result", {})

    async def list_zones(self) -> List[Zone]:
        result = await self._request("GET", f"/zones?account.id={self.account_id}")

        zones = []
        for zone in result:
            zones.append(Zone(
                id=zone["id"],
                name=zone["name"],
                status=zone["status"],
                plan=zone.get("plan", {}).get("name", "free"),
            ))

        return zones

    async def get_zone(self, zone_id: str) -> Zone:
        result = await self._request("GET", f"/zones/{zone_id}")

        return Zone(
            id=result["id"],
            name=result["name"],
            status=result["status"],
            plan=result.get("plan", {}).get("name", "free"),
        )

    async def add_zone(self, domain: str) -> Zone:
        result = await self._request("POST", "/zones", {
            "name": domain,
            "account": {"id": self.account_id},
        })

        return Zone(
            id=result["id"],
            name=result["name"],
            status=result["status"],
            plan=result.get("plan", {}).get("name", "free"),
        )

    async def list_dns_records(self, zone_id: str) -> List[DNSRecord]:
        result = await self._request("GET", f"/zones/{zone_id}/dns_records")

        records = []
        for record in result:
            records.append(DNSRecord(
                id=record["id"],
                type=record["type"],
                name=record["name"],
                content=record["content"],
                priority=record.get("priority", 0),
                ttl=record.get("ttl", 1),
                proxied=record.get("proxied", False),
            ))

        return records

    async def create_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        ttl: int = 3600,
        priority: int = 0,
        proxied: bool = False,
    ) -> DNSRecord:
        result = await self._request("POST", f"/zones/{zone_id}/dns_records", {
            "type": record_type,
            "name": name,
            "content": content,
            "ttl": ttl,
            "priority": priority,
            "proxied": proxied,
        })

        return DNSRecord(
            id=result["id"],
            type=result["type"],
            name=result["name"],
            content=result["content"],
            priority=result.get("priority", 0),
            ttl=result.get("ttl", 1),
            proxied=result.get("proxied", False),
        )

    async def delete_dns_record(self, zone_id: str, record_id: str) -> bool:
        await self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
        return True

    async def setup_email_dns(
        self,
        zone_id: str,
        server_ip: str,
        dkim_public_key: str,
        domain: str,
        dkim_selector: str = "champmail",
        dmarc_report_email: str = "",
        tracking_subdomain: str = "track",
    ) -> DNSSetupResult:
        """Create all required email DNS records for a domain.

        Records created:
          - A: mail.<domain> → server_ip
          - A: track.<domain> → server_ip  (open/click tracking pixel)
          - MX: <domain> → mail.<domain> (pri 10)
          - TXT: <domain> → SPF using server_ip directly
          - TXT: <selector>._domainkey.<domain> → DKIM public key
          - TXT: _dmarc.<domain> → DMARC policy
        """
        records = []

        try:
            # A records (mail + tracking subdomains)
            mail_a = await self.create_dns_record(
                zone_id, "A", f"mail.{domain}", server_ip, ttl=3600, proxied=False
            )
            records.append(mail_a)

            track_a = await self.create_dns_record(
                zone_id, "A", f"{tracking_subdomain}.{domain}", server_ip, ttl=3600, proxied=False
            )
            records.append(track_a)

            # MX
            mx_record = await self.create_dns_record(
                zone_id, "MX", domain, f"mail.{domain}", ttl=3600, priority=10
            )
            records.append(mx_record)

            # SPF — authorize this server's IP directly; -all = hard fail others
            spf_record = await self.create_dns_record(
                zone_id, "TXT", domain, f"v=spf1 ip4:{server_ip} -all", ttl=3600
            )
            records.append(spf_record)

            # DKIM — selector._domainkey (Cloudflare API takes just the subdomain label,
            # the zone suffix is appended automatically, so do NOT include domain here)
            dkim_record = await self.create_dns_record(
                zone_id, "TXT", f"{dkim_selector}._domainkey", dkim_public_key, ttl=3600
            )
            records.append(dkim_record)

            # DMARC
            rua = f"mailto:{dmarc_report_email}" if dmarc_report_email else ""
            rua_tag = f"; rua={rua}" if rua else ""
            dmarc_record = await self.create_dns_record(
                zone_id, "TXT", f"_dmarc", f"v=DMARC1; p=none{rua_tag}", ttl=3600
            )
            records.append(dmarc_record)

            return DNSSetupResult(success=True, records=records)

        except Exception as e:
            return DNSSetupResult(success=False, records=records, error=str(e))

    async def verify_dns_propagation(self, zone_id: str) -> PropagationStatus:
        records = await self.list_dns_records(zone_id)
        zone_name = await self.get_zone(zone_id)
        domain = zone_name.name

        mx_verified = False
        spf_verified = False
        dkim_verified = False
        dmarc_verified = False

        for record in records:
            if record.type == "MX" and record.content == f"mail.{domain}":
                mx_verified = True
            elif record.type == "TXT":
                if "v=spf1" in record.content:
                    spf_verified = True
                elif "_dmarc" in record.name:
                    dmarc_verified = True
                elif "_domainkey" in record.name:
                    dkim_verified = True

        return PropagationStatus(
            mx=mx_verified,
            spf=spf_verified,
            dkim=dkim_verified,
            dmarc=dmarc_verified,
            all_verified=mx_verified and spf_verified and dkim_verified and dmarc_verified,
        )

    async def check_domain_health(self, zone_id: str) -> Dict[str, any]:
        propagation = await self.verify_dns_propagation(zone_id)

        score = 100.0
        if not propagation.mx:
            score -= 25
        if not propagation.spf:
            score -= 25
        if not propagation.dkim:
            score -= 25
        if not propagation.dmarc:
            score -= 25

        return {
            "score": score,
            "all_verified": propagation.all_verified,
            "details": {
                "mx": propagation.mx,
                "spf": propagation.spf,
                "dkim": propagation.dkim,
                "dmarc": propagation.dmarc,
            },
        }

    async def close(self):
        await self.client.aclose()


cloudflare_client = CloudflareClient()