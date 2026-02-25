ChampMail Simplification Plan
Context
ChampMail suffers from navigation bloat (13+ items, many non-functional), unfinished features competing with core ones, broken admin uploads, and UX issues in domain management. This plan implements the PRD's 5 phases to simplify the app, stub experimental features behind "Beta" labels, and fix broken flows. All work happens on a new simple branch off main.

Pre-work: Branch Setup
Create branch simple from main: git checkout -b simple

Phase 1: Sidebar & Routing Cleanup
1.1 Create BetaBanner component
New file: frontend/src/components/ui/BetaBanner.tsx

A reusable wrapper with two modes:

status="beta" — purple info bar at page top: "This feature is in Beta" (page remains functional)
status="coming-soon" — dims page content with centered overlay card (page visible but non-interactive)
Uses existing Badge and Card components. Pattern modeled after the VoiceAgent component in WorkflowsPage.tsx:662-700.

Export from frontend/src/components/ui/index.ts.

1.2 Restructure Sidebar navigation
File: Sidebar.tsx

Split the single navigation array (line 21-34) into two groups:

Primary nav (new order per PRD):

Dashboard /
Prospects /prospects
Sequences /sequences
Templates /templates
Campaigns /campaigns
Analytics /analytics
Domains /domains
UTM Manager /utm
Test Console /send (renamed from "Send Console")
Settings /settings
Beta section (pushed to bottom with section header "Beta / Experimental"):

AI Tools (collapsible parent with Sparkles icon, Beta badge)
AI Assistant /assistant
AI Campaign Builder /ai-campaigns
Workflows /workflows (with Beta badge)
Add ChevronDown/ChevronRight imports + useState for AI Tools expand/collapse. Add superadmin to the Admin section role check (line 78).

1.3 Rename Send Console → Test Console
File: SendConsolePage.tsx — Update the Header title and subtitle. Route /send stays unchanged.

1.4 Wrap AI/Workflows pages with BetaBanner
AIAssistantPage.tsx — Wrap return in <BetaBanner status="beta" featureName="AI Assistant">
AICampaignBuilderPage.tsx — Wrap in <BetaBanner status="beta" featureName="AI Campaign Builder">
WorkflowsPage.tsx — Wrap in <BetaBanner status="beta" featureName="Workflows">
1.5 (Optional) Create AI Tools landing page
New file: frontend/src/pages/AIToolsPage.tsx — Simple page with two cards linking to AI Assistant and Campaign Builder, both badged as Beta.
Modify: App.tsx — Add route /ai-tools, pages/index.ts — Add export.

Phase 2: Role Management & Prospects Fix
2.1 Fix Admin Prospect List upload (confirmed type mismatches)
File: frontend/src/api/admin.ts

Backend vs frontend field mismatches found:

Frontend field	Backend field	Fix
UploadProspectListResponse.file_name	filename + original_filename	Rename to filename
UploadProspectListResponse.message	Not returned	Remove or make optional
UploadProspectListResponse missing	file_size, file_hash, valid_prospects, errors, warnings, headers_found, uploaded_at, uploaded_by	Add these fields
ProspectListItem.file_name	filename	Rename
ProspectListItem.total_prospects	total_rows	Rename
ProspectListItem.failed_prospects	Not in ProspectListSummary	Remove
ProspectListItem.uploaded_by	created_by	Rename
getProspectLists() returns ProspectListItem[]	Backend returns {items, total, skip, limit}	Extract .items
File: AdminProspectListsPage.tsx — Update all references to corrected field names (list.filename, list.total_rows, list.valid_prospects, list.created_by).

2.2 Implement read-only Data Team views
New file: frontend/src/hooks/usePermissions.ts


{ canEdit, canCreate, canDelete, isDataTeam, isAdmin }
Files to guard:

ProspectsPage.tsx — Hide "Add Prospect" when !canCreate
CampaignsPage.tsx — Hide "New Campaign" when !canCreate
SequencesPage.tsx — Hide "New Sequence", disable actions when !canEdit
TemplatesPage.tsx — Hide "New Template", hide delete/duplicate when !canEdit
2.3 Backend: add superadmin to role checks
File: backend/app/core/admin_security.py — Add "superadmin" to require_data_team_or_admin and require_admin role lists.

Phase 3: Domain & Templates Integration
3.1 Fix Domain Add flow UX
File: DomainManagerPage.tsx, lines 322-327

Replace the yellow AlertTriangle warning with a blue Info box:

"DNS setup can be done later. After adding the domain, share the required DNS records with your IT team. Verification runs automatically."

Change icon import from AlertTriangle to Info. Keep the Add button enabled regardless.

3.2 Integrate campaigntemplate.com into Templates
File: TemplatesPage.tsx

Add a "Professional Template Gallery" promotional card at top of page with an ExternalLink button to https://campaigntemplate.com. Uses existing Card and Button components.

Phase 4: UTM Manager Enhancement
4.1 Add "Link Generator" tab
File: UTMManagerPage.tsx

Add 5th tab { id: 'generator', label: 'Link Generator', icon: Link2 } to the existing TABS array.

4.2 Build LinkGeneratorTab component (inline in same file)
Features:

Base URL text input (any external URL)
Preset dropdown (reuses existing utmApi.getPresets())
Editable UTM fields (pre-filled from preset selection)
Live URL preview built with new URL() API
Copy-to-clipboard button
Recent history stored in localStorage (last 10 links)
Entirely client-side — no new backend endpoints needed.

Phase 5: Refactoring & Redundancy Removal
5.1 Replace scattered "coming soon" toasts with consistent UI
Search for toast.*coming soon across all pages and replace with either:

A disabled button with tooltip, or
The new BetaBanner for entire features
5.2 Extract reusable components
FileUploadZone from AdminProspectListsPage.tsx → components/ui/FileUploadZone.tsx
EmptyState from UTMManagerPage.tsx → components/ui/EmptyState.tsx
LoadingSpinner from UTMManagerPage.tsx → components/ui/LoadingSpinner.tsx
5.3 Audit unused backend endpoints
Review backend/app/api/v1/ for endpoints with zero frontend references. Add deprecation comments but don't delete yet.

Key Files Summary
File	Phases	Changes
frontend/src/components/layout/Sidebar.tsx	1	Reorder nav, add Beta section, rename Send Console
frontend/src/components/ui/BetaBanner.tsx	1	New component
frontend/src/pages/SendConsolePage.tsx	1	Rename header
frontend/src/pages/AIAssistantPage.tsx	1	Wrap with BetaBanner
frontend/src/pages/AICampaignBuilderPage.tsx	1	Wrap with BetaBanner
frontend/src/pages/WorkflowsPage.tsx	1	Wrap with BetaBanner
frontend/src/api/admin.ts	2	Fix type mismatches
frontend/src/pages/AdminProspectListsPage.tsx	2	Fix field references
frontend/src/hooks/usePermissions.ts	2	New hook
frontend/src/pages/ProspectsPage.tsx	2	Add permission guards
frontend/src/pages/CampaignsPage.tsx	2	Add permission guards
frontend/src/pages/DomainManagerPage.tsx	3	Fix DNS warning UX
frontend/src/pages/TemplatesPage.tsx	3	Add gallery link
frontend/src/pages/UTMManagerPage.tsx	4	Add Link Generator tab
backend/app/core/admin_security.py	2	Add superadmin to roles
Verification
After each phase:

Run npm run build (or pnpm build) in frontend/ to verify no TypeScript/build errors
Manually verify sidebar renders correctly with new order and Beta section
Test domain add flow completes without perceived DNS blocking
Test admin prospect upload with a sample CSV
Test UTM Link Generator with external URLs
Verify Data Team role sees read-only views (no create/edit buttons)