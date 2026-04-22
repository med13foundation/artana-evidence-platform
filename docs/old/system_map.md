🏥 Artana Resource Library - Site Map
====================================

🌐 ROOT
├── / (Home) → Redirects to /dashboard
│
├── 🔐 AUTHENTICATION (Public)
│   ├── /auth/login
│   ├── /auth/register
│   └── /auth/forgot-password
│
└── 🏠 DASHBOARD (Protected - Requires Authentication)
    │
    ├── 🏡 /dashboard (Main Dashboard - Shows Research Spaces)
    │
    ├── ⚙️ /settings (User Settings)
    │
    ├── 🛡️ SYSTEM ADMIN (Admin Role Required)
    │   ├── /system-settings (System Administration)
    │   └── /admin/data-sources/templates/
    │       ├── / (Templates List)
    │       └── /[templateId] (Template Details)
    │   └── /admin/dictionary (Kernel Dictionary Management)
    │
    └── 🏢 RESEARCH SPACES
        │
        ├── ➕ /spaces/new (Create New Space)
        │
        └── 🔬 /spaces/[spaceId]/ (Individual Space - Dynamic Routes)
            ├── 📊 / (Space Overview/Details)
            │
            ├── 💾 data-sources (Data Sources Hub)
            │   ├── 📋 Manage Existing Data Sources
            │   ├── 🔍 Discover New Sources (Add from Library)
            │   └── ➕ Create Custom Data Sources (API, Database, File Upload, Web Scraping)
            │
            ├── 🔬 curation (Data Curation & Review)
            │
            ├── 🕸️ knowledge-graph (Knowledge Graph Explorer)
            │
            ├── 📈 observations (Observation Browser)
            │
            ├── 📥 ingest (Ingestion Runner)
            │
            ├── 👥 members (Space Members Management)
            │
            └── ⚙️ settings (Space Configuration)

📡 API ENDPOINTS (Backend - FastAPI)
====================================

🔐 Authentication & Users
├── /auth/*
├── /users/*
└── /health

📊 Core Data (Kernel-Backed)
├── /api/dashboard
├── /search?space_id={spaceId} (entities/observations/relations)
└── /export/{entities|observations|relations}?space_id={spaceId}

🧠 Kernel (Space-Scoped Facts)
└── /research-spaces/{spaceId}/
    ├── entities (generic entity CRUD + resolution)
    ├── observations (typed facts / EAV with strict validation)
    ├── relations (graph edges with evidence + curation status)
    ├── graph/export (NetworkX-style graph JSON export)
    ├── graph/neighborhood/{entityId} (local neighborhood)
    ├── provenance (provenance chain)
    └── ingest (map → normalize → resolve → validate)

🔍 Data Discovery (Space-Scoped)
└── /research-spaces/{spaceId}/discovery/
    ├── catalog (Browse available sources)
    ├── sessions (Discovery session management)
    ├── presets (PubMed presets)
    └── defaults (Default parameters)

🏢 Research Spaces
├── /research-spaces/
│   ├── / (CRUD operations)
│   ├── /members (Membership management)
│   ├── /curation (Curation workflows)
│   └── /data-sources (Space data sources)

🛡️ Admin Routes
├── /admin/
│   ├── stats (System statistics)
│   ├── system-status (System health)
│   ├── catalog/ (Data catalog management)
│   ├── data-sources/ (Data source management)
│   │   ├── / (CRUD operations)
│   │   ├── /history (Ingestion history)
│   │   ├── /scheduling (Schedule management)
│   │   └── /listing (Data source listing)
│   ├── dictionary/ (Kernel dictionary management)
│   └── templates/ (Template management)
│       ├── / (Template CRUD)
│       └── /mutations (Template operations)

💾 Storage & Infrastructure
├── /admin/storage/configurations
└── /resources

🎯 NAVIGATION FLOW
=================

1. Public Access → Authentication Required
   Landing → Login/Register → Dashboard

2. Dashboard Navigation
   ├── Header: MED13 Admin + Space Selector + User Menu
   ├── Dashboard Content: Displays all research spaces in a grid layout
   ├── Space Navigation: Overview | Data Sources | Data Curation | Knowledge Graph | ⋮ (Members, Settings)
   │   └── Data Sources: Comprehensive hub for all data source activities
   │       ├── View & manage existing data sources
   │       ├── "Add from Library" - Browse & test pre-configured sources (PubMed, etc.)
   │       └── "Create Custom Source" - Add manual integrations (API, Database, File, Web Scraping)
   └── Breadcrumbs: Dynamic based on current path (excludes "Research Spaces" segment)

3. Space Context
   ├── All navigation adapts based on selected research space
   ├── Space-specific data and permissions
   └── Context-aware breadcrumbs and navigation

4. Admin Features
   ├── System Settings (Admin-only)
   ├── Data Source Templates
   └── Global configuration management

🔄 USER ROLES & ACCESS CONTROL
==============================

MED13 has **two layers of access**:

1. **System roles** control platform-wide features.
   Admins can open admin-only pages such as System Settings, Audit Logs, Dictionary, and PHI Access.
2. **Research space roles** control what a person can do inside a specific space.
   Owner/Admin manage the space, Curator reviews work, Researcher creates work, and Viewer has read-only access.

For the full user-friendly role matrix, see:

- `docs/onboarding/user-roles-and-access.md`

🔒 Protected Routes
├── Automatic redirects to login for unauthenticated users
├── Role-based access control for admin features
└── Space membership validation for space-specific routes
