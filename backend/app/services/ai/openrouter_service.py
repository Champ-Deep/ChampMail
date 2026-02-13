"""
Unified OpenRouter AI service.
All AI operations go through OpenRouter - Perplexity for research, Claude for generation.
"""

import json
import asyncio
from typing import Dict, List, Optional
import httpx
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.redis import redis_client


class OpenRouterClient:
    """Base client for all OpenRouter API calls."""

    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.timeout = settings.openrouter_timeout

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        response_format: Optional[Dict] = None,
    ) -> str:
        """Call OpenRouter chat completions API."""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://champmail.dev",
                    "X-Title": "ChampMail",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())


class ResearchService(OpenRouterClient):
    """Prospect research using Perplexity via OpenRouter."""

    def __init__(self):
        super().__init__()
        self.model = settings.research_model
        self.cache_ttl_days = settings.research_cache_ttl_days

    def _cache_key(self, prospect_id: str) -> str:
        return f"research:prospect:{prospect_id}"

    async def research_prospect(self, prospect: Dict) -> Dict:
        """Research a single prospect using Perplexity Sonar."""
        prospect_id = prospect.get("id")

        # Check cache
        if prospect_id:
            cached = await redis_client.get_json(self._cache_key(prospect_id))
            if cached:
                return cached

        company = prospect.get("company_name", "Unknown Company")
        name = f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip() or "the contact"
        title = prospect.get("title") or prospect.get("job_title", "professional")
        domain = prospect.get("company_domain", "")

        prompt = f"""Research this B2B prospect for a cold email campaign. Return structured JSON only.

Company: {company}
Person: {name}
Title: {title}
{f"Domain: {domain}" if domain else ""}

Return JSON with these exact keys:
{{
  "company_info": {{
    "description": "brief company description",
    "industry": "industry/sector",
    "size": "estimated employee count",
    "revenue": "estimated revenue range",
    "products": ["key products/services"],
    "tech_stack": ["known technologies"],
    "recent_news": ["last 6 months developments"]
  }},
  "industry_insights": {{
    "trends": ["current trends"],
    "pain_points": ["common challenges"],
    "regulatory": ["relevant regulations/changes"]
  }},
  "persona_details": {{
    "responsibilities": ["typical responsibilities for {title}"],
    "challenges": ["common challenges"],
    "priorities": ["key metrics/goals"],
    "decision_authority": "level of buying authority"
  }},
  "triggers": {{
    "funding": "recent funding info or null",
    "acquisitions": "recent M&A or null",
    "leadership_changes": "recent exec changes or null",
    "hiring": ["relevant job postings"],
    "expansion": "growth signals"
  }},
  "personalization_hooks": ["3-5 specific details useful for email personalization"]
}}"""

        try:
            content = await self.chat_completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3,
            )

            try:
                research_data = self._parse_json_response(content)
            except json.JSONDecodeError:
                research_data = {
                    "company_info": {"description": content[:500]},
                    "industry_insights": {},
                    "persona_details": {},
                    "triggers": {},
                    "personalization_hooks": [],
                    "raw_response": content,
                }

            research_data["_metadata"] = {
                "researched_at": datetime.utcnow().isoformat(),
                "model": self.model,
                "prospect_id": prospect_id,
            }

            if prospect_id:
                ttl = self.cache_ttl_days * 86400
                await redis_client.set_json(self._cache_key(prospect_id), research_data, ex=ttl)

            return research_data

        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "company_info": {"description": f"Unable to research {company}"},
                "industry_insights": {},
                "persona_details": {},
                "triggers": {},
                "personalization_hooks": [],
            }
        except Exception as e:
            return {
                "error": str(e),
                "company_info": {"description": f"Research failed for {company}"},
                "industry_insights": {},
                "persona_details": {},
                "triggers": {},
                "personalization_hooks": [],
            }

    async def research_batch(self, prospects: List[Dict], concurrency: int = 3) -> List[Dict]:
        """Research batch of prospects with controlled concurrency."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _research_with_limit(prospect):
            async with semaphore:
                research = await self.research_prospect(prospect)
                return {
                    "prospect_id": prospect.get("id"),
                    "prospect_email": prospect.get("email"),
                    "research_data": research,
                }

        tasks = [_research_with_limit(p) for p in prospects]
        return await asyncio.gather(*tasks)

    async def invalidate_cache(self, prospect_id: str):
        """Invalidate cached research."""
        await redis_client.delete(self._cache_key(prospect_id))


class SegmentationService(OpenRouterClient):
    """AI-powered prospect segmentation using Claude via OpenRouter."""

    def __init__(self):
        super().__init__()
        self.model = settings.segmentation_model

    async def segment_prospects(
        self,
        research_data: List[Dict],
        campaign_goals: str,
        campaign_essence: Dict,
    ) -> Dict:
        """Create intelligent segments from research data."""
        system_prompt = "You are an expert B2B marketing strategist. Analyze prospect data and create intelligent segments. Always respond with valid JSON only."

        prompt = f"""Analyze prospect research and create 3-8 segments for a B2B email campaign.

**Campaign Goals:** {campaign_goals}

**Campaign Essence:**
- Value Props: {json.dumps(campaign_essence.get('value_propositions', []))}
- Pain Points: {json.dumps(campaign_essence.get('pain_points', []))}
- Tone: {campaign_essence.get('tone', 'professional')}

**Prospect Research (sample of {len(research_data)}):**
{json.dumps(research_data[:15], indent=2, default=str)}

Return JSON:
{{
  "segments": [
    {{
      "id": "seg_1",
      "name": "Descriptive Segment Name",
      "criteria": {{
        "industries": ["Industry1"],
        "roles": ["Role1", "Role2"],
        "company_size": ["range"],
        "key_indicators": ["indicator"]
      }},
      "size_estimate_pct": 25,
      "characteristics": "Description of segment",
      "pain_points": ["specific pain point"],
      "messaging_angle": "How to position for this segment",
      "priority": "high/medium/low"
    }}
  ],
  "strategy": "Overall segmentation rationale",
  "unmatched_pct": 5
}}"""

        content = await self.chat_completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.5,
        )

        try:
            return self._parse_json_response(content)
        except json.JSONDecodeError:
            return {
                "segments": [{
                    "id": "seg_fallback",
                    "name": "All Prospects",
                    "criteria": {},
                    "size_estimate_pct": 100,
                    "characteristics": "All prospects",
                    "pain_points": [],
                    "messaging_angle": "General value proposition",
                    "priority": "medium",
                }],
                "strategy": "Fallback due to parsing error",
                "unmatched_pct": 0,
            }


class CampaignEssenceService(OpenRouterClient):
    """Extract campaign essence from user description."""

    def __init__(self):
        super().__init__()
        self.model = settings.general_model

    async def extract_essence(
        self,
        user_input: str,
        target_audience: Optional[str] = None,
    ) -> Dict:
        """Extract campaign framework from user description."""
        system_prompt = "You are an expert B2B copywriter. Extract campaign messaging frameworks. Respond with valid JSON only."

        audience_line = f"\n**Target Audience:** {target_audience}" if target_audience else ""

        prompt = f"""Extract the core campaign essence from this description.

**Campaign Description:**
{user_input}
{audience_line}

Return JSON:
{{
  "value_propositions": ["3-5 key benefits"],
  "pain_points": ["3-5 problems addressed"],
  "call_to_action": "primary CTA",
  "tone": "tone description",
  "unique_angle": "what makes this campaign different",
  "target_persona": "ideal recipient description"
}}"""

        content = await self.chat_completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.6,
        )

        try:
            return self._parse_json_response(content)
        except json.JSONDecodeError:
            return {
                "value_propositions": ["Key benefit"],
                "pain_points": ["Problem addressed"],
                "call_to_action": "Learn more",
                "tone": "professional",
                "unique_angle": "",
                "target_persona": target_audience or "",
            }


class PitchService(OpenRouterClient):
    """Generate segment-specific pitches and personalize for prospects."""

    def __init__(self):
        super().__init__()
        self.model = settings.pitch_model

    async def generate_pitch(
        self,
        segment: Dict,
        campaign_essence: Dict,
        sample_research: List[Dict],
    ) -> Dict:
        """Generate segment-specific email pitch."""
        system_prompt = "You are an expert B2B cold email copywriter. Create highly personalized, concise email pitches. Respond with valid JSON only."

        prompt = f"""Create a targeted email pitch for this segment.

**Segment:** {segment.get('name')}
- Characteristics: {segment.get('characteristics')}
- Pain Points: {json.dumps(segment.get('pain_points', []))}
- Messaging Angle: {segment.get('messaging_angle')}

**Campaign Essence:**
- Value Props: {json.dumps(campaign_essence.get('value_propositions', []))}
- CTA: {campaign_essence.get('call_to_action')}
- Tone: {campaign_essence.get('tone')}

**Sample Prospects:**
{json.dumps(sample_research[:3], indent=2, default=str)}

Available variables: {{{{firstName}}}}, {{{{lastName}}}}, {{{{companyName}}}}, {{{{industry}}}}, {{{{title}}}}, {{{{recentNews}}}}, {{{{relevantDetail}}}}

Return JSON:
{{
  "pitch_angle": "one-sentence positioning",
  "key_messages": ["3-4 bullet points"],
  "subject_lines": [
    "Subject line 1 with {{{{firstName}}}} and {{{{companyName}}}}",
    "Subject line 2",
    "Subject line 3"
  ],
  "body_template": "Hi {{{{firstName}}}},\\n\\nOpening hook...\\n\\nValue prop...\\n\\nCTA...\\n\\nBest,\\n[Sender]",
  "follow_up_templates": [
    {{
      "delay_days": 3,
      "subject": "Re: previous subject",
      "body": "Follow-up body..."
    }},
    {{
      "delay_days": 7,
      "subject": "Quick follow-up",
      "body": "Second follow-up..."
    }}
  ],
  "personalization_variables": ["firstName", "companyName", "recentNews"]
}}

Keep body under 120 words. Make it feel personal, not templated."""

        content = await self.chat_completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.8,
        )

        try:
            return self._parse_json_response(content)
        except json.JSONDecodeError:
            return {
                "pitch_angle": "Value-focused outreach",
                "key_messages": ["Key benefit"],
                "subject_lines": ["{{firstName}}, quick question for {{companyName}}"],
                "body_template": "Hi {{firstName}},\n\nReaching out about {{companyName}}...",
                "follow_up_templates": [],
                "personalization_variables": ["firstName", "companyName"],
            }

    def personalize_for_prospect(
        self,
        pitch: Dict,
        prospect: Dict,
        research_data: Dict,
    ) -> Dict:
        """Replace template variables with prospect-specific data."""
        company_info = research_data.get("company_info", {})
        if isinstance(company_info, str):
            company_info = {"description": company_info}

        triggers = research_data.get("triggers", {})
        hooks = research_data.get("personalization_hooks", [])

        variables = {
            "firstName": prospect.get("first_name", "there"),
            "lastName": prospect.get("last_name", ""),
            "fullName": f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip() or "there",
            "companyName": prospect.get("company_name", "your company"),
            "industry": company_info.get("industry", prospect.get("industry", "your industry")),
            "title": prospect.get("title") or prospect.get("job_title", ""),
            "role": prospect.get("title") or prospect.get("job_title", ""),
            "recentNews": hooks[0] if hooks else (triggers.get("expansion") or "is growing"),
            "relevantDetail": hooks[1] if len(hooks) > 1 else company_info.get("description", "")[:100],
        }

        subject = (pitch.get("subject_lines") or [""])[0]
        body = pitch.get("body_template", "")

        for var_name, var_value in variables.items():
            placeholder = "{{" + var_name + "}}"
            subject = subject.replace(placeholder, str(var_value))
            body = body.replace(placeholder, str(var_value))

        follow_ups = []
        for fu in pitch.get("follow_up_templates", []):
            fu_subject = fu.get("subject", "")
            fu_body = fu.get("body", "")
            for var_name, var_value in variables.items():
                placeholder = "{{" + var_name + "}}"
                fu_subject = fu_subject.replace(placeholder, str(var_value))
                fu_body = fu_body.replace(placeholder, str(var_value))
            follow_ups.append({
                "delay_days": fu.get("delay_days", 3),
                "subject": fu_subject,
                "body": fu_body,
            })

        return {
            "subject": subject,
            "body": body,
            "follow_ups": follow_ups,
            "variables_used": variables,
        }


class HTMLGenerationService(OpenRouterClient):
    """Generate HTML emails from text pitches."""

    def __init__(self):
        super().__init__()
        self.model = settings.html_model

    async def generate_html(
        self,
        subject: str,
        body_text: str,
        prospect: Dict,
        campaign_style: Optional[Dict] = None,
    ) -> str:
        """Generate mobile-responsive HTML email."""
        style = campaign_style or {}
        primary_color = style.get("primary_color", "#2563eb")
        company_name = style.get("company_name", "ChampMail")

        system_prompt = "You are an expert email designer. Create beautiful, mobile-responsive HTML emails compatible with Gmail, Outlook, and Apple Mail. Output ONLY raw HTML starting with <!DOCTYPE html>."

        prompt = f"""Convert this email into professional HTML.

**Subject:** {subject}

**Body Text:**
{body_text}

**Recipient:**
- Name: {prospect.get('first_name', '')} {prospect.get('last_name', '')}
- Company: {prospect.get('company_name', '')}

**Design Specs:**
- Table-based layout (email client compatibility)
- 600px max width, centered
- Mobile responsive with media queries
- Inline CSS only
- Primary color: {primary_color}
- Text color: #1e293b
- Background: #f8fafc
- Clean B2B aesthetic, Lake B2B inspired
- Include: preheader, header, body, CTA button, footer
- Footer must include: {{{{unsubscribe_url}}}} link
- Add tracking pixel: <img src="{{{{tracking_url}}}}" width="1" height="1" alt="" style="display:none"/>
- Bulletproof CTA button
- Company: {company_name}

Output the complete HTML only, starting with <!DOCTYPE html>."""

        content = await self.chat_completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.6,
        )

        html = content.strip()
        if html.startswith("```html"):
            html = html[7:]
        if html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]

        return html.strip()


# Singleton instances
research_service = ResearchService()
segmentation_service = SegmentationService()
essence_service = CampaignEssenceService()
pitch_service = PitchService()
html_service = HTMLGenerationService()
