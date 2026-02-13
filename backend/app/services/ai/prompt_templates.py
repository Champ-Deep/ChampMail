"""
Prompt templates for AI operations.
Centralized prompt engineering for consistency and easy iteration.
"""

# Research Prompts

PROSPECT_RESEARCH_PROMPT = """Research the following B2B prospect for a cold email campaign:

Company: {company_name}
Person: {person_name}
Title: {title}
{domain_line}

Please provide:

1. **Company Information:**
   - Brief company description and main business
   - Industry and market segment
   - Company size (estimated employees/revenue if available)
   - Recent news or significant developments (last 6 months)
   - Technology stack or key products (if applicable)

2. **Industry Context:**
   - Current trends in their industry
   - Common pain points for companies in this sector
   - Regulatory or market changes affecting them

3. **Role/Persona Details:**
   - Typical responsibilities for a {title}
   - Common challenges they face
   - What they care about (metrics, goals, priorities)
   - Decision-making authority

4. **Relevant Triggers:**
   - Recent funding, acquisitions, or leadership changes
   - New product launches or expansions
   - Hiring trends (especially relevant roles)
   - Technology migrations or digital transformation initiatives

Please structure the output as JSON with keys: company_info, industry_insights, persona_details, triggers."""

# Segmentation Prompts

SEGMENTATION_SYSTEM_PROMPT = """You are an expert B2B marketing strategist specializing in account-based marketing and prospect segmentation. Your task is to analyze prospect research data and create intelligent segments for targeted campaigns."""

SEGMENTATION_PROMPT = """Analyze the following prospect research data and create 3-8 intelligent segments for a B2B email campaign.

**Campaign Goals:**
{campaign_goals}

**Campaign Essence:**
- Value Propositions: {value_propositions}
- Pain Points Addressed: {pain_points}
- Tone: {tone}

**Prospect Research Data:**
{research_data_sample}

**Instructions:**
1. Identify patterns across prospects (industry, role, company size, pain points, triggers)
2. Create 3-8 segments that group similar prospects
3. For each segment, provide:
   - **Name**: Clear, descriptive segment name
   - **Criteria**: Specific characteristics that define this segment
   - **Size Estimate**: Approximate % of total prospects
   - **Key Characteristics**: Industry, role, company profile
   - **Pain Points**: Specific challenges this segment faces
   - **Messaging Angle**: How to position the campaign for this segment
   - **AI Reasoning**: Why this segment exists and what makes it distinct

**Output Format (JSON):**
```json
{{
  "segments": [
    {{
      "name": "Enterprise Tech CTOs",
      "criteria": {{
        "industries": ["Technology", "SaaS"],
        "roles": ["CTO", "VP Engineering"],
        "company_size": ["201-1000", "1000+"],
        "key_indicators": ["recent funding", "scaling team"]
      }},
      "size_estimate": 25,
      "key_characteristics": "Large tech companies in growth phase...",
      "pain_points": ["Email deliverability at scale", "Infrastructure complexity"],
      "messaging_angle": "Enterprise-grade reliability and compliance",
      "ai_reasoning": "This segment represents technical decision-makers..."
    }}
  ],
  "segmentation_strategy": "Overall approach and rationale",
  "coverage": {{
    "total_prospects": {total_prospects},
    "segmented": "estimated number"
  }}
}}
```

Respond with ONLY the JSON object, no additional text."""

# Campaign Essence Prompts

CAMPAIGN_ESSENCE_SYSTEM_PROMPT = """You are an expert B2B copywriter who excels at distilling campaign goals into clear, actionable messaging frameworks."""

CAMPAIGN_ESSENCE_PROMPT = """Analyze the following campaign description and extract the core essence for email marketing.

**Campaign Description:**
{user_input}

{target_audience_line}

**Extract:**
1. **Value Propositions**: 3-5 key benefits or unique selling points
2. **Pain Points**: 3-5 problems this campaign addresses
3. **Call to Action**: Primary desired action (demo, trial, meeting, download, etc.)
4. **Tone**: Overall tone (professional, friendly, urgent, consultative, technical, etc.)

**Output Format (JSON):**
```json
{{
  "value_propositions": [
    "Improve email deliverability by 40%",
    "Reduce bounce rates with AI-powered validation",
    "Scale campaigns without compromising inbox placement"
  ],
  "pain_points": [
    "Emails landing in spam folders",
    "High bounce rates damaging sender reputation",
    "Manual list cleaning is time-consuming"
  ],
  "call_to_action": "Schedule a demo",
  "tone": "professional and consultative"
}}
```

Respond with ONLY the JSON object."""

# Pitch Generation Prompts

PITCH_GENERATION_SYSTEM_PROMPT = """You are an expert B2B email copywriter known for crafting compelling, personalized cold email campaigns that drive engagement."""

PITCH_GENERATION_PROMPT = """Create a highly effective email pitch for this specific segment.

**Segment:**
- Name: {segment_name}
- Characteristics: {segment_characteristics}
- Pain Points: {segment_pain_points}
- Messaging Angle: {segment_angle}

**Campaign Essence:**
- Value Props: {value_propositions}
- Addresses: {pain_points}
- CTA: {call_to_action}
- Tone: {tone}

**Sample Prospects:**
{sample_research}

**Create:**
1. **Pitch Angle**: One-sentence positioning for this segment
2. **Key Messages**: 3-4 bullet points to emphasize
3. **Subject Line Template**: With {{variable}} placeholders (e.g., {{firstName}}, {{companyName}})
4. **Body Template**: Email body with {{variable}} placeholders
   - Opening hook (referencing company/role)
   - Problem/pain point
   - Solution/value prop (1-2 sentences)
   - Social proof or credential (1 sentence)
   - Clear CTA
   - Max 120 words

**Available Variables:**
- {{firstName}}, {{lastName}}, {{fullName}}
- {{companyName}}, {{industry}}
- {{title}}, {{role}}
- {{recentNews}} (from research)
- {{relevantDetail}} (company-specific insight)

**Output Format (JSON):**
```json
{{
  "pitch_angle": "One-sentence positioning",
  "key_messages": ["Message 1", "Message 2", "Message 3"],
  "subject_template": "{{firstName}}, quick question about {{companyName}}'s deliverability",
  "body_template": "Hi {{firstName}},\\n\\nI noticed {{companyName}} recently {{recentNews}}...\\n\\n[Rest of email]",
  "personalization_variables": ["firstName", "companyName", "recentNews", "role", "industry"]
}}
```

Keep it concise, specific to the segment, and highly personalizable. Respond with ONLY JSON."""

# HTML Generation Prompts

HTML_GENERATION_SYSTEM_PROMPT = """You are an expert email designer who creates beautiful, mobile-responsive HTML emails that render perfectly across all email clients (Gmail, Outlook, Apple Mail, etc.)."""

HTML_GENERATION_PROMPT = """Create a professional HTML email from this text content.

**Text Content:**
{pitch_text}

**Prospect Context:**
- Name: {prospect_name}
- Company: {company_name}
- Title: {title}

**Design Requirements:**
1. Mobile-responsive (Gmail, Outlook, Apple Mail compatible)
2. Clean, professional B2B aesthetic
3. Inspired by: {campaign_template_reference}
4. Lake B2B style: Clean, minimal, focused on content
5. Include:
   - Preheader text (hidden but shown in preview)
   - Proper email header
   - Body content with good typography
   - Clear CTA button (styled properly)
   - Footer with unsubscribe link: {{{{unsubscribe_url}}}}
   - Tracking pixel: <img src="{{{{tracking_url}}}}" width="1" height="1" />

**Technical Requirements:**
- Use table-based layout for compatibility
- Inline CSS (no external stylesheets)
- Alt text for images
- Bulletproof buttons
- 600px max width
- Proper DOCTYPE and meta tags

**Color Palette:**
- Primary: #2563eb (blue)
- Secondary: #64748b (slate gray)
- Background: #ffffff
- Text: #1e293b

Output ONLY the complete HTML code, starting with <!DOCTYPE html>."""


# Helper functions for prompt building

def build_research_prompt(prospect: dict) -> str:
    """Build prospect research prompt with variable substitution."""
    company = prospect.get("company_name", "Unknown Company")
    name = f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip() or "the person"
    title = prospect.get("title", "professional")
    domain = prospect.get("company_domain", "")

    domain_line = f"Domain: {domain}" if domain else ""

    return PROSPECT_RESEARCH_PROMPT.format(
        company_name=company,
        person_name=name,
        title=title,
        domain_line=domain_line
    )


def build_segmentation_prompt(
    campaign_goals: str,
    campaign_essence: dict,
    research_data_sample: str,
    total_prospects: int
) -> str:
    """Build segmentation prompt."""
    return SEGMENTATION_PROMPT.format(
        campaign_goals=campaign_goals,
        value_propositions=campaign_essence.get("value_propositions", []),
        pain_points=campaign_essence.get("pain_points", []),
        tone=campaign_essence.get("tone", "professional"),
        research_data_sample=research_data_sample,
        total_prospects=total_prospects
    )


def build_campaign_essence_prompt(
    user_input: str,
    target_audience: str = None
) -> str:
    """Build campaign essence extraction prompt."""
    target_audience_line = f"**Target Audience:** {target_audience}" if target_audience else ""

    return CAMPAIGN_ESSENCE_PROMPT.format(
        user_input=user_input,
        target_audience_line=target_audience_line
    )


def build_pitch_prompt(
    segment: dict,
    campaign_essence: dict,
    sample_research: str
) -> str:
    """Build pitch generation prompt."""
    return PITCH_GENERATION_PROMPT.format(
        segment_name=segment.get("name"),
        segment_characteristics=segment.get("key_characteristics"),
        segment_pain_points=segment.get("pain_points"),
        segment_angle=segment.get("messaging_angle"),
        value_propositions=campaign_essence.get("value_propositions"),
        pain_points=campaign_essence.get("pain_points"),
        call_to_action=campaign_essence.get("call_to_action"),
        tone=campaign_essence.get("tone"),
        sample_research=sample_research
    )


def build_html_prompt(
    pitch_text: str,
    prospect: dict,
    campaign_template_reference: str = "https://campaigntemplate.com/"
) -> str:
    """Build HTML generation prompt."""
    return HTML_GENERATION_PROMPT.format(
        pitch_text=pitch_text,
        prospect_name=f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
        company_name=prospect.get("company_name", ""),
        title=prospect.get("title", ""),
        campaign_template_reference=campaign_template_reference
    )
