import httpx
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SendResult:
    message_id: str
    status: str
    domain_id: str
    sent_at: datetime


@dataclass
class BatchResult:
    total: int
    successful: int
    failed: int
    results: List[SendResult]


@dataclass
class DNSCheckResult:
    domain: str
    mx_records: List[str]
    spf_valid: bool
    dkim_selector: str
    dkim_valid: bool
    dmarc_valid: bool
    all_verified: bool


@dataclass
class DKIMKeys:
    domain: str
    selector: str
    private_key: str
    public_key: str


@dataclass
class SendStats:
    domain_id: str
    today_sent: int
    today_limit: int
    total_sent: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    open_rate: float
    click_rate: float
    bounce_rate: float


@dataclass
class BounceRecord:
    id: str
    email: str
    bounce_type: str
    smtp_response: str
    domain_id: str


class MailEngineClient:
    def __init__(self):
        self.base_url = os.getenv("MAIL_ENGINE_URL", "http://localhost:8025")
        self.api_key = os.getenv("MAIL_ENGINE_API_KEY", "")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        response = await self.client.request(
            method, url, json=data, headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()

    async def send_email(
        self,
        recipient: str,
        recipient_name: str = "",
        subject: str = "",
        html_body: str = "",
        text_body: str = "",
        from_address: str = "",
        reply_to: str = "",
        domain_id: str = "",
        track_opens: bool = True,
        track_clicks: bool = True,
    ) -> SendResult:
        data = {
            "to": recipient,
            "from": from_address,
            "from_name": recipient_name,
            "subject": subject,
            "html_body": html_body,
            "text_body": text_body,
            "reply_to": reply_to,
            "domain_id": domain_id,
            "track_opens": track_opens,
            "track_clicks": track_clicks,
        }

        result = await self._request("POST", "/send", data)

        return SendResult(
            message_id=result["message_id"],
            status=result["status"],
            domain_id=result.get("domain_id", ""),
            sent_at=datetime.fromisoformat(result["sent_at"].replace("Z", "+00:00")),
        )

    async def send_batch(
        self, emails: List[Dict[str, Any]], domain_id: str = ""
    ) -> BatchResult:
        data = {"emails": emails, "domain_id": domain_id}

        result = await self._request("POST", "/send/batch", data)

        results = [
            SendResult(
                message_id=r["message_id"],
                status=r["status"],
                domain_id=r.get("domain_id", ""),
                sent_at=datetime.fromisoformat(r["sent_at"].replace("Z", "+00:00")),
            )
            for r in result["results"]
        ]

        return BatchResult(
            total=result["total"],
            successful=result["successful"],
            failed=result["failed"],
            results=results,
        )

    async def get_send_status(self, message_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/send/status/{message_id}")

    async def get_send_stats(self, domain_id: str = "") -> SendStats:
        params = f"?domain_id={domain_id}" if domain_id else ""
        result = await self._request("GET", f"/send/stats{params}")

        return SendStats(
            domain_id=result["domain_id"],
            today_sent=result["today_sent"],
            today_limit=result["total_sent"],
            total_sent=result["total_sent"],
            total_opened=result["total_opened"],
            total_clicked=result["total_clicked"],
            total_bounced=result["total_bounced"],
            open_rate=result["open_rate"],
            click_rate=result["click_rate"],
            bounce_rate=result["bounce_rate"],
        )

    async def verify_domain(self, domain_id: str) -> DNSCheckResult:
        result = await self._request("POST", f"/domains/{domain_id}/verify")

        return DNSCheckResult(
            domain=result["domain"],
            mx_records=result.get("mx_records", []),
            spf_valid=result.get("spf_valid", False),
            dkim_selector=result.get("dkim_selector", ""),
            dkim_valid=result.get("dkim_valid", False),
            dmarc_valid=result.get("dmarc_valid", False),
            all_verified=result.get("all_verified", False),
        )

    async def generate_dkim_keys(
        self, domain: str, selector: str = "champmail"
    ) -> DKIMKeys:
        result = await self._request("POST", "/domains/dkim/generate", {"domain": domain, "selector": selector})

        return DKIMKeys(
            domain=result["domain"],
            selector=result["selector"],
            private_key=result["private_key"],
            public_key=result["public_key"],
        )

    async def get_dns_records(self, domain_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", f"/domains/{domain_id}/dns-records")

    async def get_domain_health(self, domain_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/domains/{domain_id}/health")

    async def list_domains(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/domains")

    async def create_domain(self, domain_name: str, selector: str = "champmail") -> Dict[str, Any]:
        return await self._request("POST", "/domains", {"domain_name": domain_name, "selector": selector})

    async def get_bounces(self, limit: int = 100) -> List[BounceRecord]:
        return await self._request("GET", f"/bounces?limit={limit}")

    async def acknowledge_bounce(self, bounce_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/bounces/{bounce_id}/acknowledge")

    async def check_for_replies(self, prospect_email: str) -> bool:
        result = await self._request("GET", f"/replies/check?email={prospect_email}")
        return result.get("has_replied", False)


mail_engine_client = MailEngineClient()