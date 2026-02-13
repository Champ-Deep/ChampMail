"""
UTM Tracking Service.

Handles UTM parameter resolution, HTML link injection, auto-generation
of campaign UTM configs, link metadata recording, and click tracking.

Template variables supported in UTM fields:
  {{campaign_name}}       - Full campaign name
  {{campaign_name_slug}}  - Slugified campaign name
  {{segment}} / {{segment_name}} - Segment name (slugified)
  {{prospect_company}}    - Prospect company name (slugified)
  {{prospect_name}}       - Prospect full/first name
  {{date}}                - Today's date (YYYY-MM-DD)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import async_session_maker
from app.models.campaign import Campaign
from app.models.utm import CampaignUTMConfig, LinkClick, UTMPreset

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug.

    Lowercases, replaces non-alphanumeric sequences with hyphens,
    and strips leading/trailing hyphens.
    """
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class UTMService:
    """Service for UTM parameter management and link tracking."""

    # ------------------------------------------------------------------
    # Resolve UTM template variables
    # ------------------------------------------------------------------

    async def resolve_utm_params(
        self,
        campaign_id: str,
        prospect_data: Optional[Dict[str, Any]],
        segment_name: Optional[str],
        session: AsyncSession,
    ) -> Dict[str, str]:
        """Resolve UTM parameters for a campaign, substituting template variables.

        Looks up the CampaignUTMConfig first; falls back to the team's
        default UTMPreset if the config is missing or disabled.

        Parameters
        ----------
        campaign_id : str
            Campaign UUID.
        prospect_data : dict or None
            Prospect fields (company_name, first_name, full_name, etc.).
        segment_name : str or None
            Name of the prospect segment/list being sent to.
        session : AsyncSession
            Active database session.

        Returns
        -------
        dict
            Resolved UTM parameters with only non-empty values.
            Keys are "utm_source", "utm_medium", etc.
        """
        prospect_data = prospect_data or {}

        # 1. Try campaign-specific config
        result = await session.execute(
            select(CampaignUTMConfig).where(
                CampaignUTMConfig.campaign_id == campaign_id
            )
        )
        config = result.scalar_one_or_none()

        utm_source = ""
        utm_medium = ""
        utm_campaign = ""
        utm_content = ""
        utm_term = ""

        if config and config.enabled:
            utm_source = config.utm_source or ""
            utm_medium = config.utm_medium or ""
            utm_campaign = config.utm_campaign or ""
            utm_content = config.utm_content or ""
            utm_term = config.utm_term or ""
        else:
            # 2. Fall back to team's default preset
            # We need the campaign to find team_id
            campaign_result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if not campaign or not campaign.team_id:
                return {}

            preset_result = await session.execute(
                select(UTMPreset).where(
                    UTMPreset.team_id == campaign.team_id,
                    UTMPreset.is_default == True,  # noqa: E712
                )
            )
            preset = preset_result.scalar_one_or_none()
            if not preset:
                return {}

            utm_source = preset.utm_source or ""
            utm_medium = preset.utm_medium or ""
            utm_campaign = preset.utm_campaign or ""
            utm_content = preset.utm_content or ""
            utm_term = preset.utm_term or ""

        # 3. Fetch campaign name for template variables
        campaign_result = await session.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        campaign_name = campaign.name if campaign else ""

        # 4. Build replacement map
        replacements = {
            "{{campaign_name}}": campaign_name,
            "{{campaign_name_slug}}": _slugify(campaign_name),
            "{{segment}}": _slugify(segment_name or ""),
            "{{segment_name}}": _slugify(segment_name or ""),
            "{{prospect_company}}": _slugify(prospect_data.get("company_name", "") or ""),
            "{{prospect_name}}": prospect_data.get("full_name", "") or prospect_data.get("first_name", "") or "",
            "{{date}}": datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # 5. Substitute templates in each field
        def _apply_templates(value: str) -> str:
            for template, replacement in replacements.items():
                value = value.replace(template, replacement)
            return value.strip()

        resolved = {}
        for key, raw_value in [
            ("utm_source", utm_source),
            ("utm_medium", utm_medium),
            ("utm_campaign", utm_campaign),
            ("utm_content", utm_content),
            ("utm_term", utm_term),
        ]:
            final = _apply_templates(raw_value)
            if final:
                resolved[key] = final

        return resolved

    # ------------------------------------------------------------------
    # Inject UTM params into HTML links
    # ------------------------------------------------------------------

    def inject_utm_into_html(
        self,
        html_body: str,
        utm_params: Dict[str, str],
        preserve_existing: bool = True,
        link_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Inject UTM parameters into all trackable links in an HTML email body.

        Parameters
        ----------
        html_body : str
            HTML email body string.
        utm_params : dict
            Base UTM parameters to inject (e.g. {"utm_source": "champmail"}).
        preserve_existing : bool
            If True, skip links that already contain utm_ query params.
        link_overrides : dict or None
            Map of URL-substring -> UTM overrides. If a link URL contains
            a key from this dict, those UTM values are merged (override base).

        Returns
        -------
        tuple[str, list[dict]]
            (modified_html, links_metadata) where links_metadata is a list
            of dicts with original_url, tracked_url, anchor_text, position, etc.
        """
        link_overrides = link_overrides or {}
        links_metadata: List[Dict[str, Any]] = []
        position_counter = 0

        # Pattern matches <a ...href="URL"...>inner content</a>
        link_pattern = re.compile(
            r'(<a\s[^>]*href=["\'])([^"\']+)(["\'][^>]*>)(.*?)(</a>)',
            re.IGNORECASE | re.DOTALL,
        )

        def _strip_html_tags(text: str) -> str:
            """Remove HTML tags from inner anchor content."""
            return re.sub(r"<[^>]+>", "", text).strip()

        def _replace_link(match: re.Match) -> str:
            nonlocal position_counter

            prefix = match.group(1)
            url = match.group(2)
            mid = match.group(3)
            inner = match.group(4)
            suffix = match.group(5)

            # Skip non-trackable URLs
            lower_url = url.lower()
            if any(lower_url.startswith(skip) for skip in ("mailto:", "tel:", "javascript:")):
                return match.group(0)

            # Skip template variables
            if "{{" in url or "}}" in url:
                return match.group(0)

            # Skip tracking/pixel/unsubscribe URLs
            skip_keywords = ("tracking", "pixel", "unsubscribe", "track/open", "track/click")
            if any(kw in lower_url for kw in skip_keywords):
                return match.group(0)

            # Parse existing URL
            parsed = urlparse(url)

            # If preserve_existing and URL already has utm_ params, skip
            if preserve_existing:
                existing_qs = parse_qs(parsed.query)
                if any(k.startswith("utm_") for k in existing_qs):
                    return match.group(0)

            # Start with base UTM params
            final_params = dict(utm_params)

            # Apply link-specific overrides
            for pattern_key, overrides in link_overrides.items():
                if pattern_key in url:
                    final_params.update(overrides)

            # Merge params into existing query string
            existing_qs = parse_qs(parsed.query, keep_blank_values=True)
            for k, v in final_params.items():
                existing_qs[k] = [v]

            new_query = urlencode(existing_qs, doseq=True)
            new_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            ))

            anchor_text = _strip_html_tags(inner)
            idx = position_counter
            position_counter += 1

            # Build link metadata
            meta: Dict[str, Any] = {
                "original_url": url,
                "tracked_url": new_url,
                "anchor_text": anchor_text[:500] if anchor_text else None,
                "position": idx,
            }
            # Copy final UTM params into metadata
            for utm_key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
                meta[utm_key] = final_params.get(utm_key)

            links_metadata.append(meta)

            return f"{prefix}{new_url}{mid}{inner}{suffix}"

        modified_html = link_pattern.sub(_replace_link, html_body)
        return modified_html, links_metadata

    # ------------------------------------------------------------------
    # Auto-generate campaign UTM config
    # ------------------------------------------------------------------

    async def auto_generate_config(
        self,
        campaign_id: str,
        team_id: str,
        session: AsyncSession,
    ) -> CampaignUTMConfig:
        """Auto-generate a CampaignUTMConfig for a campaign.

        If one already exists, returns it. Otherwise creates one from the
        team's default UTMPreset (creating a default preset if needed).

        Parameters
        ----------
        campaign_id : str
            Campaign UUID.
        team_id : str
            Team UUID.
        session : AsyncSession
            Active database session.

        Returns
        -------
        CampaignUTMConfig
            The existing or newly created config.
        """
        # Check if config already exists
        result = await session.execute(
            select(CampaignUTMConfig).where(
                CampaignUTMConfig.campaign_id == campaign_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Find team's default preset
        preset_result = await session.execute(
            select(UTMPreset).where(
                UTMPreset.team_id == team_id,
                UTMPreset.is_default == True,  # noqa: E712
            )
        )
        preset = preset_result.scalar_one_or_none()

        # Create default preset if none exists
        if not preset:
            preset = UTMPreset(
                id=uuid4(),
                team_id=team_id,
                name="Default UTM Preset",
                is_default=True,
                utm_source="champmail",
                utm_medium="email",
                utm_campaign="{{campaign_name_slug}}",
                utm_content="{{segment}}",
                utm_term="{{prospect_company}}",
            )
            session.add(preset)
            await session.flush()

        # Create campaign config from preset
        config = CampaignUTMConfig(
            id=uuid4(),
            campaign_id=campaign_id,
            preset_id=preset.id,
            enabled=True,
            utm_source=preset.utm_source,
            utm_medium=preset.utm_medium,
            utm_campaign=preset.utm_campaign,
            utm_content=preset.utm_content,
            utm_term=preset.utm_term,
            team_id=team_id,
        )
        session.add(config)
        await session.flush()

        logger.info(
            "Auto-generated UTM config for campaign=%s team=%s",
            campaign_id,
            team_id,
        )
        return config

    # ------------------------------------------------------------------
    # Record link metadata (bulk insert)
    # ------------------------------------------------------------------

    async def record_link_metadata(
        self,
        links: List[Dict[str, Any]],
        campaign_id: str,
        prospect_id: Optional[str],
        send_log_id: Optional[str],
        team_id: str,
        session: AsyncSession,
    ) -> None:
        """Bulk-create LinkClick records from extracted link metadata.

        Parameters
        ----------
        links : list[dict]
            List of link metadata dicts from inject_utm_into_html().
        campaign_id : str
            Campaign UUID.
        prospect_id : str or None
            Prospect UUID if available.
        send_log_id : str or None
            SendLog UUID if available.
        team_id : str
            Team UUID.
        session : AsyncSession
            Active database session.
        """
        for link_meta in links:
            link_click = LinkClick(
                id=uuid4(),
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                send_log_id=send_log_id,
                original_url=link_meta["original_url"],
                tracked_url=link_meta.get("tracked_url"),
                anchor_text=link_meta.get("anchor_text"),
                link_position=link_meta.get("position"),
                utm_source=link_meta.get("utm_source"),
                utm_medium=link_meta.get("utm_medium"),
                utm_campaign=link_meta.get("utm_campaign"),
                utm_content=link_meta.get("utm_content"),
                utm_term=link_meta.get("utm_term"),
                click_count=0,
                unique_clicks=0,
                team_id=team_id,
            )
            session.add(link_click)

        await session.flush()

    # ------------------------------------------------------------------
    # Increment link click
    # ------------------------------------------------------------------

    async def increment_link_click(
        self,
        original_url: str,
        campaign_id: str,
        prospect_id: Optional[str],
    ) -> None:
        """Increment click counts for a link.

        Opens its own database session (for use from webhook handlers).

        Parameters
        ----------
        original_url : str
            The original URL that was clicked.
        campaign_id : str
            Campaign UUID.
        prospect_id : str or None
            Prospect UUID if available.
        """
        now = datetime.utcnow()

        async with async_session_maker() as session:
            # Build query conditions
            conditions = [
                LinkClick.campaign_id == campaign_id,
                LinkClick.original_url == original_url,
            ]
            if prospect_id:
                conditions.append(LinkClick.prospect_id == prospect_id)

            result = await session.execute(
                select(LinkClick).where(*conditions)
            )
            link_click = result.scalar_one_or_none()

            if link_click:
                was_zero = link_click.click_count == 0

                link_click.click_count = (link_click.click_count or 0) + 1
                link_click.last_clicked_at = now

                if was_zero:
                    link_click.unique_clicks = (link_click.unique_clicks or 0) + 1

                if link_click.first_clicked_at is None:
                    link_click.first_clicked_at = now

                await session.commit()

                logger.info(
                    "Link click incremented: campaign=%s url=%s prospect=%s",
                    campaign_id,
                    original_url[:80],
                    prospect_id,
                )
            else:
                logger.warning(
                    "LinkClick record not found: campaign=%s url=%s prospect=%s",
                    campaign_id,
                    original_url[:80],
                    prospect_id,
                )


# Singleton instance
utm_service = UTMService()
