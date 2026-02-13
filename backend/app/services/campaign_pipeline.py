"""
Campaign Pipeline Orchestrator.

Orchestrates the full AI campaign pipeline: essence extraction, prospect research,
segmentation, pitch generation, personalization, and HTML email generation.

Stores intermediate results in Redis so the frontend can poll progress in real-time.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import async_session_maker
from app.db.redis import redis_client
from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.services.ai.openrouter_service import (
    essence_service,
    html_service,
    pitch_service,
    research_service,
    segmentation_service,
)

logger = logging.getLogger(__name__)

# Pipeline status constants
PIPELINE_STATUS_PENDING = "pending"
PIPELINE_STATUS_RUNNING = "running"
PIPELINE_STATUS_COMPLETED = "completed"
PIPELINE_STATUS_FAILED = "failed"

# Pipeline step names
STEP_ESSENCE = "extract_essence"
STEP_RESEARCH = "research_prospects"
STEP_SEGMENT = "segment_prospects"
STEP_PITCH = "generate_pitches"
STEP_PERSONALIZE = "personalize_emails"
STEP_HTML = "generate_html"

ALL_STEPS = [STEP_ESSENCE, STEP_RESEARCH, STEP_SEGMENT, STEP_PITCH, STEP_PERSONALIZE, STEP_HTML]

# Redis key TTL: 24 hours for pipeline data
PIPELINE_TTL = 86400


class CampaignPipeline:
    """Orchestrates the full AI campaign pipeline.

    Each step stores its results in Redis under deterministic keys so that:
    - The frontend can poll status via `pipeline:{campaign_id}:status`
    - Individual step results are accessible via `pipeline:{campaign_id}:{step_name}`
    - The full result set lives at `pipeline:{campaign_id}:results`
    """

    # ------------------------------------------------------------------ #
    #  Redis helpers
    # ------------------------------------------------------------------ #

    def _key(self, campaign_id: str, suffix: str) -> str:
        return f"pipeline:{campaign_id}:{suffix}"

    async def _set_status(
        self,
        campaign_id: str,
        status: str,
        step: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> None:
        """Update the pipeline status in Redis for frontend polling."""
        payload: Dict[str, Any] = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if step:
            payload["current_step"] = step
            payload["step_index"] = ALL_STEPS.index(step) if step in ALL_STEPS else -1
            payload["total_steps"] = len(ALL_STEPS)
        if progress is not None:
            payload["progress"] = progress
        if error:
            payload["error"] = error
        if meta:
            payload.update(meta)

        await redis_client.set_json(self._key(campaign_id, "status"), payload, ex=PIPELINE_TTL)

    async def _store_step_result(self, campaign_id: str, step: str, data: Any) -> None:
        """Persist an individual step result to Redis."""
        await redis_client.set_json(self._key(campaign_id, step), data, ex=PIPELINE_TTL)

    async def get_pipeline_status(self, campaign_id: str) -> Optional[dict]:
        """Public method: fetch current pipeline status (for API layer)."""
        return await redis_client.get_json(self._key(campaign_id, "status"))

    async def get_step_result(self, campaign_id: str, step: str) -> Optional[dict]:
        """Public method: fetch the result of a specific pipeline step."""
        return await redis_client.get_json(self._key(campaign_id, step))

    async def get_all_results(self, campaign_id: str) -> Optional[dict]:
        """Public method: fetch the full pipeline results."""
        return await redis_client.get_json(self._key(campaign_id, "results"))

    # ------------------------------------------------------------------ #
    #  Full pipeline
    # ------------------------------------------------------------------ #

    async def run_full_pipeline(
        self,
        campaign_id: str,
        prospect_list_id: str,
        description: str,
        target_audience: Optional[str] = None,
        style: Optional[dict] = None,
    ) -> dict:
        """Run the complete pipeline end-to-end.

        Parameters
        ----------
        campaign_id : str
            UUID of the Campaign row.
        prospect_list_id : str
            Used to look up prospects enrolled in the campaign (via team or list).
        description : str
            User-provided campaign description (fed into essence extraction).
        target_audience : str, optional
            Free-text description of the target audience.
        style : dict, optional
            Visual style overrides for HTML generation (primary_color, company_name, etc.).

        Returns
        -------
        dict
            Full results payload with keys for each step.
        """
        pipeline_run_id = str(uuid4())
        started_at = datetime.utcnow().isoformat()

        logger.info("Pipeline %s starting for campaign %s", pipeline_run_id, campaign_id)

        try:
            await self._set_status(
                campaign_id,
                PIPELINE_STATUS_RUNNING,
                step=STEP_ESSENCE,
                progress=0,
                meta={"run_id": pipeline_run_id, "started_at": started_at},
            )

            # --- Step 1: Extract campaign essence ---
            essence = await self.extract_essence(description, target_audience)
            await self._store_step_result(campaign_id, STEP_ESSENCE, essence)
            await self._set_status(campaign_id, PIPELINE_STATUS_RUNNING, step=STEP_RESEARCH, progress=15)

            # --- Step 2: Load prospects & research ---
            prospect_dicts = await self._load_prospects(campaign_id, prospect_list_id)
            if not prospect_dicts:
                raise ValueError("No prospects found for this campaign / prospect list")

            prospect_ids = [p["id"] for p in prospect_dicts]
            research_results = await self.research_prospects(prospect_ids, campaign_id=campaign_id)
            await self._store_step_result(campaign_id, STEP_RESEARCH, research_results)
            await self._set_status(campaign_id, PIPELINE_STATUS_RUNNING, step=STEP_SEGMENT, progress=35)

            # --- Step 3: Segment prospects ---
            segments = await self.segment_prospects(
                research_results,
                campaign_goals=description,
                essence=essence,
            )
            await self._store_step_result(campaign_id, STEP_SEGMENT, segments)
            await self._set_status(campaign_id, PIPELINE_STATUS_RUNNING, step=STEP_PITCH, progress=50)

            # --- Step 4: Generate pitches per segment ---
            pitches = await self.generate_pitches(segments, essence, research_results)
            await self._store_step_result(campaign_id, STEP_PITCH, pitches)
            await self._set_status(campaign_id, PIPELINE_STATUS_RUNNING, step=STEP_PERSONALIZE, progress=65)

            # --- Step 5: Personalize for each prospect ---
            research_lookup = self._build_research_lookup(research_results)
            personalized = await self.personalize_emails(pitches, prospect_dicts, research_lookup)
            await self._store_step_result(campaign_id, STEP_PERSONALIZE, personalized)
            await self._set_status(campaign_id, PIPELINE_STATUS_RUNNING, step=STEP_HTML, progress=80)

            # --- Step 6: Generate HTML emails ---
            html_emails = await self.generate_html_emails(personalized, style=style)
            await self._store_step_result(campaign_id, STEP_HTML, html_emails)

            # --- Persist personalized content to DB ---
            await self._persist_results(campaign_id, html_emails)

            # Build final results payload
            results = {
                "run_id": pipeline_run_id,
                "campaign_id": campaign_id,
                "started_at": started_at,
                "completed_at": datetime.utcnow().isoformat(),
                "total_prospects": len(prospect_dicts),
                "total_emails_generated": len(html_emails),
                "essence": essence,
                "segments": segments,
                "pitches_by_segment": {k: v for k, v in pitches.items() if k != "_meta"},
                "emails": html_emails,
            }

            await redis_client.set_json(self._key(campaign_id, "results"), results, ex=PIPELINE_TTL)
            await self._set_status(
                campaign_id,
                PIPELINE_STATUS_COMPLETED,
                progress=100,
                meta={
                    "run_id": pipeline_run_id,
                    "started_at": started_at,
                    "completed_at": datetime.utcnow().isoformat(),
                    "total_emails": len(html_emails),
                },
            )

            # Update campaign status in DB
            await self._update_campaign_status(campaign_id, "active")

            logger.info(
                "Pipeline %s completed for campaign %s: %d emails generated",
                pipeline_run_id,
                campaign_id,
                len(html_emails),
            )
            return results

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            logger.error("Pipeline %s failed: %s\n%s", pipeline_run_id, error_msg, traceback.format_exc())
            await self._set_status(
                campaign_id,
                PIPELINE_STATUS_FAILED,
                error=error_msg,
                meta={"run_id": pipeline_run_id, "started_at": started_at},
            )
            await self._update_campaign_status(campaign_id, "draft")
            raise

    # ------------------------------------------------------------------ #
    #  Individual pipeline steps
    # ------------------------------------------------------------------ #

    async def extract_essence(
        self,
        description: str,
        target_audience: Optional[str] = None,
    ) -> dict:
        """Step 1: Extract campaign essence from user description.

        Uses the CampaignEssenceService to distill value props, pain points,
        tone, CTA, and target persona from a free-text campaign description.
        """
        logger.info("Extracting campaign essence (desc length=%d)", len(description))

        essence = await essence_service.extract_essence(description, target_audience)

        logger.info(
            "Essence extracted: %d value props, tone=%s",
            len(essence.get("value_propositions", [])),
            essence.get("tone", "unknown"),
        )
        return essence

    async def research_prospects(
        self,
        prospect_ids: List[str],
        campaign_id: Optional[str] = None,
    ) -> list:
        """Step 2: Research prospects via Perplexity.

        Loads prospect records from the database, then sends them through the
        ResearchService in batches with controlled concurrency.
        """
        logger.info("Researching %d prospects", len(prospect_ids))

        # Load prospect dicts from DB
        async with async_session_maker() as session:
            result = await session.execute(
                select(Prospect).where(Prospect.id.in_(prospect_ids))
            )
            prospects = result.scalars().all()

        prospect_dicts = [
            {
                "id": str(p.id),
                "email": p.email,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "company_name": p.company_name,
                "company_domain": p.company_domain,
                "title": p.job_title,
                "job_title": p.job_title,
                "industry": p.industry,
            }
            for p in prospects
        ]

        # Research in batches (the service already handles concurrency internally)
        batch_size = 10
        all_results: list = []
        for i in range(0, len(prospect_dicts), batch_size):
            batch = prospect_dicts[i : i + batch_size]
            batch_results = await research_service.research_batch(batch, concurrency=3)
            all_results.extend(batch_results)

            if campaign_id:
                pct = min(35, 15 + int(20 * (i + len(batch)) / len(prospect_dicts)))
                await self._set_status(
                    campaign_id,
                    PIPELINE_STATUS_RUNNING,
                    step=STEP_RESEARCH,
                    progress=pct,
                    meta={"researched": len(all_results), "total": len(prospect_dicts)},
                )

        logger.info("Research completed: %d results", len(all_results))
        return all_results

    async def segment_prospects(
        self,
        research_results: list,
        campaign_goals: str,
        essence: dict,
    ) -> dict:
        """Step 3: AI-powered segmentation of researched prospects.

        Takes the research results and campaign essence, then uses the
        SegmentationService to create intelligent segments.
        """
        logger.info("Segmenting %d researched prospects", len(research_results))

        segments = await segmentation_service.segment_prospects(
            research_data=research_results,
            campaign_goals=campaign_goals,
            campaign_essence=essence,
        )

        segment_count = len(segments.get("segments", []))
        logger.info("Segmentation complete: %d segments created", segment_count)
        return segments

    async def generate_pitches(
        self,
        segments: dict,
        essence: dict,
        research_results: list,
    ) -> dict:
        """Step 4: Generate a pitch template for each segment.

        For each segment, selects a sample of matching research data and
        generates a segment-specific email pitch via the PitchService.
        """
        segment_list = segments.get("segments", [])
        logger.info("Generating pitches for %d segments", len(segment_list))

        pitches: Dict[str, Any] = {}

        for segment in segment_list:
            seg_id = segment.get("id", str(uuid4()))

            # Pick sample research to inform the pitch
            sample_research = self._sample_research_for_segment(
                research_results, segment, max_samples=3
            )

            pitch = await pitch_service.generate_pitch(
                segment=segment,
                campaign_essence=essence,
                sample_research=sample_research,
            )

            pitches[seg_id] = {
                "segment": segment,
                "pitch": pitch,
            }

        logger.info("Pitches generated for %d segments", len(pitches))
        return pitches

    async def personalize_emails(
        self,
        pitches: dict,
        prospects: list,
        research_data: dict,
    ) -> list:
        """Step 5: Personalize pitch templates for each individual prospect.

        Assigns each prospect to the best-matching segment, then fills in
        personalization variables using their research data.

        Parameters
        ----------
        pitches : dict
            Mapping of segment_id -> {"segment": ..., "pitch": ...}
        prospects : list[dict]
            Prospect dictionaries with standard fields.
        research_data : dict
            Mapping of prospect_id -> research dict.

        Returns
        -------
        list[dict]
            One entry per prospect with subject, body, follow_ups, prospect info.
        """
        logger.info("Personalizing emails for %d prospects", len(prospects))

        personalized: list = []
        segment_list = [v["segment"] for v in pitches.values()]
        pitch_lookup = {v["segment"].get("id"): v["pitch"] for v in pitches.values()}

        for prospect in prospects:
            prospect_id = prospect.get("id", "")
            p_research = research_data.get(prospect_id, {})

            # Assign prospect to best segment
            best_seg_id = self._assign_to_segment(prospect, p_research, segment_list)
            pitch = pitch_lookup.get(best_seg_id)

            if not pitch:
                # Fallback: use the first available pitch
                pitch = next(iter(pitch_lookup.values()), {})

            # Use PitchService's personalization
            result = pitch_service.personalize_for_prospect(
                pitch=pitch,
                prospect=prospect,
                research_data=p_research,
            )

            personalized.append({
                "prospect_id": prospect_id,
                "prospect_email": prospect.get("email"),
                "prospect": prospect,
                "segment_id": best_seg_id,
                "subject": result.get("subject", ""),
                "body": result.get("body", ""),
                "follow_ups": result.get("follow_ups", []),
                "variables_used": result.get("variables_used", {}),
            })

        logger.info("Personalization complete: %d emails", len(personalized))
        return personalized

    async def generate_html_emails(
        self,
        personalized_emails: list,
        style: Optional[dict] = None,
    ) -> list:
        """Step 6: Generate HTML-formatted emails from personalized text.

        Calls the HTMLGenerationService for each personalized email with
        controlled concurrency to avoid overwhelming the API.
        """
        logger.info("Generating HTML for %d emails", len(personalized_emails))

        semaphore = asyncio.Semaphore(3)
        results: list = []

        async def _generate_one(item: dict) -> dict:
            async with semaphore:
                try:
                    html = await html_service.generate_html(
                        subject=item["subject"],
                        body_text=item["body"],
                        prospect=item.get("prospect", {}),
                        campaign_style=style,
                    )
                    return {
                        **item,
                        "html_body": html,
                        "html_generated": True,
                    }
                except Exception as exc:
                    logger.warning(
                        "HTML generation failed for prospect %s: %s",
                        item.get("prospect_id"),
                        str(exc),
                    )
                    return {
                        **item,
                        "html_body": self._fallback_html(item["subject"], item["body"]),
                        "html_generated": False,
                        "html_error": str(exc),
                    }

        tasks = [_generate_one(email) for email in personalized_emails]
        results = await asyncio.gather(*tasks)

        generated_count = sum(1 for r in results if r.get("html_generated"))
        logger.info("HTML generation complete: %d/%d succeeded", generated_count, len(results))
        return list(results)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    async def _load_prospects(self, campaign_id: str, prospect_list_id: str) -> list:
        """Load prospect dicts from CampaignProspect enrollments or direct lookup."""
        async with async_session_maker() as session:
            # First try: look up via CampaignProspect enrollment table
            result = await session.execute(
                select(Prospect)
                .join(CampaignProspect, CampaignProspect.prospect_id == Prospect.id)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(Prospect.status == "active")
            )
            prospects = result.scalars().all()

            # Fallback: load by prospect_list_id treated as team_id
            if not prospects and prospect_list_id:
                result = await session.execute(
                    select(Prospect)
                    .where(Prospect.team_id == prospect_list_id)
                    .where(Prospect.status == "active")
                )
                prospects = result.scalars().all()

        return [
            {
                "id": str(p.id),
                "email": p.email,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "full_name": p.full_name,
                "company_name": p.company_name,
                "company_domain": p.company_domain,
                "company_size": p.company_size,
                "industry": p.industry,
                "job_title": p.job_title,
                "title": p.job_title,
                "linkedin_url": p.linkedin_url,
                "team_id": str(p.team_id) if p.team_id else None,
            }
            for p in prospects
        ]

    async def _persist_results(self, campaign_id: str, html_emails: list) -> None:
        """Write personalized subjects and HTML bodies back to Prospect + CampaignProspect."""
        async with async_session_maker() as session:
            for email_data in html_emails:
                prospect_id = email_data.get("prospect_id")
                if not prospect_id:
                    continue

                # Update Prospect with personalized content
                await session.execute(
                    update(Prospect)
                    .where(Prospect.id == prospect_id)
                    .values(
                        personalized_subject=email_data.get("subject"),
                        personalized_body=email_data.get("html_body"),
                        updated_at=datetime.utcnow(),
                    )
                )

                # Update CampaignProspect status to ready
                await session.execute(
                    update(CampaignProspect)
                    .where(CampaignProspect.campaign_id == campaign_id)
                    .where(CampaignProspect.prospect_id == prospect_id)
                    .values(status="active")
                )

            await session.commit()

        logger.info("Persisted %d personalized emails to database", len(html_emails))

    async def _update_campaign_status(self, campaign_id: str, status: str) -> None:
        """Update the Campaign row's status in PostgreSQL."""
        async with async_session_maker() as session:
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values(status=status, updated_at=datetime.utcnow())
            )
            await session.commit()

    def _build_research_lookup(self, research_results: list) -> dict:
        """Convert a list of research results into a {prospect_id: research_data} dict."""
        lookup = {}
        for item in research_results:
            pid = item.get("prospect_id")
            if pid:
                lookup[pid] = item.get("research_data", {})
        return lookup

    def _sample_research_for_segment(
        self,
        research_results: list,
        segment: dict,
        max_samples: int = 3,
    ) -> list:
        """Pick a sample of research results that plausibly belong to a segment.

        Uses simple heuristics: matching industry or role keywords.
        """
        criteria = segment.get("criteria", {})
        target_industries = [i.lower() for i in criteria.get("industries", [])]
        target_roles = [r.lower() for r in criteria.get("roles", [])]

        scored: list = []
        for item in research_results:
            research = item.get("research_data", {})
            company_info = research.get("company_info", {})
            if isinstance(company_info, str):
                company_info = {"description": company_info}

            score = 0
            industry = (company_info.get("industry") or "").lower()
            if any(t in industry for t in target_industries):
                score += 2

            persona = research.get("persona_details", {})
            responsibilities = " ".join(persona.get("responsibilities", [])).lower()
            if any(r in responsibilities for r in target_roles):
                score += 1

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:max_samples]]

    def _assign_to_segment(
        self,
        prospect: dict,
        research_data: dict,
        segments: list,
    ) -> str:
        """Assign a prospect to the best-matching segment via simple scoring."""
        if not segments:
            return ""

        best_seg_id = segments[0].get("id", "")
        best_score = -1

        industry = (prospect.get("industry") or "").lower()
        title = (prospect.get("job_title") or prospect.get("title") or "").lower()
        company_size = (prospect.get("company_size") or "").lower()

        company_info = research_data.get("company_info", {})
        if isinstance(company_info, str):
            company_info = {}
        research_industry = (company_info.get("industry") or "").lower()

        for seg in segments:
            score = 0
            criteria = seg.get("criteria", {})

            # Industry match
            seg_industries = [i.lower() for i in criteria.get("industries", [])]
            if any(si in industry or si in research_industry for si in seg_industries):
                score += 3

            # Role match
            seg_roles = [r.lower() for r in criteria.get("roles", [])]
            if any(sr in title for sr in seg_roles):
                score += 3

            # Company size match
            seg_sizes = [s.lower() for s in criteria.get("company_size", [])]
            if any(ss in company_size for ss in seg_sizes):
                score += 1

            # Priority bonus
            priority = seg.get("priority", "medium").lower()
            if priority == "high":
                score += 1

            if score > best_score:
                best_score = score
                best_seg_id = seg.get("id", "")

        return best_seg_id

    def _fallback_html(self, subject: str, body_text: str) -> str:
        """Generate a minimal fallback HTML email when AI generation fails."""
        escaped_body = (
            body_text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f8fafc;font-family:Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc;">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;">
<tr><td style="padding:32px;color:#1e293b;font-size:16px;line-height:1.6;">
{escaped_body}
</td></tr>
<tr><td style="padding:0 32px 32px;text-align:center;font-size:12px;color:#94a3b8;">
<a href="{{{{unsubscribe_url}}}}" style="color:#94a3b8;">Unsubscribe</a>
</td></tr>
</table>
</td></tr>
</table>
<img src="{{{{tracking_url}}}}" width="1" height="1" alt="" style="display:none"/>
</body>
</html>"""


# Singleton instance
campaign_pipeline = CampaignPipeline()
