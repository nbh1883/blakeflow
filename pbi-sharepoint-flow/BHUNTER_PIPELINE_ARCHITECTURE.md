# BHunter Data Pipeline — Architecture & Implementation Guide

> **⚠️ "BHunter" is a placeholder company name used throughout this documentation.** Before deploying, find-and-replace all instances of `BHunter`, `bhunter`, and `bhunter.com` with your actual company name and domain. This applies to distribution lists, shared mailboxes, SharePoint site references, Azure resource names, Teams channels, and Power Automate flow names.

## System Overview

An automated, event-driven pipeline that extracts data from Power BI, lands it in SharePoint, and triggers downstream actions (notifications, routing, anomaly detection, digests) via Power Automate. Designed for agent orchestration from day one — every component returns structured data and exposes clean interfaces for programmatic control.

---

## Component Map

| Component | File | Purpose | Owner |
|---|---|---|---|
| Data Extraction + SharePoint Upload | `pbi_data_pull.py` | Auth, DAX query, Excel build, Graph API upload | Python / Azure Function |
| Script Documentation | `PBI_DATA_PULL_README.md` | Setup, config, agent patterns, LLM revision guide | Reference |
| Power Automate Flows | `BHUNTER_POWER_AUTOMATE_FLOWS.md` | 4 flow specs: notification, routing, digest, anomaly | Power Automate |
| Pipeline Architecture | `BHUNTER_PIPELINE_ARCHITECTURE.md` | This document — master reference | Reference |

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SCHEDULING / TRIGGER LAYER                        │
│                                                                          │
│   Azure Function          Power Automate           Agent (SK/AutoGen)    │
│   (Timer Trigger)         (Recurrence)             (On-demand)           │
│        │                       │                        │                │
│        └───────────┬───────────┘────────────────────────┘                │
│                    ▼                                                     │
│              pbi_data_pull.run()                                         │
└──────────────┬───────────────────────────────────────────────────────────┘
               │
               │  Returns: { status, tables_pulled, total_rows, ... }
               │
┌──────────────▼───────────────────────────────────────────────────────────┐
│                         DATA LAYER                                       │
│                                                                          │
│   ┌─────────────────┐     ┌───────────────────────┐                     │
│   │  Power BI        │     │  SharePoint             │                   │
│   │  REST API        │     │  /Shared Documents/     │                   │
│   │  (executeQueries)│────▶│  PBI Extracts/          │                   │
│   │                  │     │    ├─ extract.xlsx       │                   │
│   │  DAX → JSON →    │     │    └─ extract_meta.json  │                   │
│   │  DataFrame →     │     │                         │                   │
│   │  Excel bytes     │     │  (Graph API upload)     │                   │
│   └─────────────────┘     └───────────┬─────────────┘                   │
│                                       │                                  │
└───────────────────────────────────────┼──────────────────────────────────┘
                                        │
                    SharePoint file trigger fires
                                        │
┌───────────────────────────────────────▼──────────────────────────────────┐
│                      AUTOMATION LAYER (Power Automate)                    │
│                                                                          │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│   │ Flow 1       │  │ Flow 2       │  │ Flow 3   │  │ Flow 4        │  │
│   │ File Drop    │  │ Conditional  │  │ Weekly   │  │ Anomaly       │  │
│   │ Notification │  │ Routing      │  │ Digest   │  │ Alert         │  │
│   │              │  │              │  │          │  │               │  │
│   │ Email + Teams│  │ Route by     │  │ Batch    │  │ Compare row   │  │
│   │ on every     │  │ filename     │  │ summary  │  │ counts to     │  │
│   │ file drop    │  │ prefix to    │  │ of all   │  │ previous run; │  │
│   │              │  │ team-specific│  │ weekly   │  │ flag >20%     │  │
│   │              │  │ DLs          │  │ extracts │  │ changes       │  │
│   └──────────────┘  └──────────────┘  └──────────┘  └───────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      CONSUMERS                                           │
│                                                                          │
│   📧 Email (shared mailbox)     💬 Teams (#data-alerts)                 │
│   📊 Stakeholder inboxes        🤖 Copilot Studio (future: chat Q&A)   │
│   📁 SharePoint (browse/download)                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Core Pipeline (Week 1–2)

**Goal:** Data flows from PBI to SharePoint automatically; stakeholders get notified.

| Step | Task | Effort | Dependencies |
|---|---|---|---|
| 1.1 | Azure AD app registration + permissions | 1 hr | Global Admin for consent |
| 1.2 | Configure `pbi_data_pull.py` with BHunter credentials | 30 min | Step 1.1 |
| 1.3 | Create SharePoint folder structure | 15 min | SharePoint site access |
| 1.4 | Test script locally — verify Excel + SharePoint upload | 1 hr | Steps 1.2, 1.3 |
| 1.5 | Deploy script to Azure Function (timer trigger) | 2 hr | Azure subscription |
| 1.6 | Move secrets to Azure Key Vault | 1 hr | Azure subscription |
| 1.7 | Build + deploy Flow 1 (file drop notification) | 1 hr | Power Automate license |
| 1.8 | Create shared mailbox + distribution lists | 30 min | Exchange admin |
| 1.9 | End-to-end test: trigger Azure Function → file lands → email fires | 30 min | All above |

**Deliverable:** Automated daily PBI extract → SharePoint → email notification.

### Phase 2: Smart Routing + Digest (Week 3–4)

**Goal:** Notifications are targeted; noise is reduced.

| Step | Task | Effort | Dependencies |
|---|---|---|---|
| 2.1 | Define filename prefix conventions per dataset | 30 min | Team alignment |
| 2.2 | Build + deploy Flow 2 (conditional routing) | 2 hr | Step 2.1 |
| 2.3 | Build + deploy Flow 3 (weekly digest) | 2 hr | Phase 1 complete |
| 2.4 | Optional: create routing config SharePoint list | 1 hr | Cleaner than hardcoded conditions |
| 2.5 | Decide notification strategy: per-file vs digest vs both | — | Team preference |

**Deliverable:** Right people get the right files; weekly summary replaces notification fatigue.

### Phase 3: Anomaly Detection + Metadata (Week 5–6)

**Goal:** Pipeline is self-aware — flags data quality issues automatically.

| Step | Task | Effort | Dependencies |
|---|---|---|---|
| 3.1 | Modify `pbi_data_pull.py` to export metadata sidecar JSON | 1 hr | Script access |
| 3.2 | Test sidecar upload alongside Excel | 30 min | Step 3.1 |
| 3.3 | Build + deploy Flow 4 (anomaly alert) | 3 hr | Step 3.2 |
| 3.4 | Tune anomaly threshold (start at 20%, adjust based on signal) | Ongoing | Step 3.3 |
| 3.5 | Optional: add Adaptive Cards in Teams for interactive alerts | 2 hr | Teams connector |

**Deliverable:** Automatic anomaly detection with email + Teams alerts.

### Phase 4: Agent Intelligence (Week 7+)

**Goal:** Move from reactive automation to proactive intelligence.

| Step | Task | Effort | Dependencies |
|---|---|---|---|
| 4.1 | Evaluate Copilot Studio vs Semantic Kernel for agent layer | — | Licensing, infra |
| 4.2 | Build comparison module: current vs. previous extract analysis | 4 hr | Phase 3 metadata |
| 4.3 | Natural language summary generation (AI Builder or API call) | 4 hr | AI Builder license or Anthropic API |
| 4.4 | Copilot Studio agent for stakeholder Q&A against extracts | 8 hr | Copilot Studio license |
| 4.5 | Multi-dataset orchestration: parallel pulls, merged reports | 4 hr | Multiple PBI datasets |
| 4.6 | Self-healing pipeline: auto-retry, ticket creation on failure | 4 hr | ITSM integration |

**Deliverable:** Intelligent agent that summarizes, compares, and answers questions about the data.

---

## Environment Setup

### Azure Resources Required

| Resource | Purpose | SKU / Notes |
|---|---|---|
| Azure Function App | Hosts `pbi_data_pull.py` on a timer | Consumption plan (free tier covers this) |
| Azure Key Vault | Stores TENANT_ID, CLIENT_ID, CLIENT_SECRET | Standard |
| Azure AD App Registration | Service Principal for PBI + Graph auth | Free |
| SharePoint Site | File destination | Existing BHunter site or new subsite |

### Licensing Required

| Product | License | Who Needs It |
|---|---|---|
| Power Automate | Premium (if using HTTP connector to call Azure Function) or standard (if SharePoint trigger only) | Flow owner (service account) |
| Power BI | Pro or PPU (for API access to datasets) | Service Principal needs workspace access, not a license |
| Microsoft 365 | E3/E5 or equivalent | For SharePoint, Outlook, Teams connectors |
| Azure | Pay-as-you-go | For Function App + Key Vault (minimal cost) |

### Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Azure Function | `func-bhunter-pbi-{env}` | `func-bhunter-pbi-prod` |
| Key Vault | `kv-bhunter-{env}` | `kv-bhunter-prod` |
| App Registration | `BHunter-PBI-DataPull-{env}` | `BHunter-PBI-DataPull-Prod` |
| SharePoint folder | `/Shared Documents/PBI Extracts/` | — |
| Excel files | `{prefix}_extract_{timestamp}.xlsx` | `sales_extract_20260323_060000.xlsx` |
| Metadata files | `{prefix}_extract_{timestamp}_meta.json` | `sales_extract_20260323_060000_meta.json` |
| Power Automate flows | `BHunter — {flow name}` | `BHunter — File Drop Notification` |
| Distribution lists | `bhunter-{team}@bhunter.com` | `bhunter-data-team@bhunter.com` |
| Shared mailbox | `datapipeline@bhunter.com` | — |

---

## Security Model

```
┌─────────────────────────────────────────────┐
│          Azure Key Vault                    │
│  ├─ PBI-TENANT-ID                           │
│  ├─ PBI-CLIENT-ID                           │
│  └─ PBI-CLIENT-SECRET                       │
│         │                                   │
│         │ Managed Identity                  │
│         ▼                                   │
│  Azure Function App                         │
│  (reads secrets at runtime)                 │
└─────────────────────────────────────────────┘
         │
         │ Service Principal (app registration)
         ├──→ Power BI API: Dataset.Read.All (Application)
         └──→ Graph API: Sites.ReadWrite.All (Application)
```

### Access Control Principles

1. **Least privilege**: SP gets Viewer on PBI workspace, ReadWrite on the specific SharePoint site only.
2. **No hardcoded secrets**: Key Vault + Managed Identity for the Azure Function.
3. **Scoped SP enablement**: PBI admin setting scoped to a security group, not tenant-wide.
4. **Shared mailbox for notifications**: No individual account dependency.
5. **Audit trail**: Azure AD sign-in logs track every SP authentication event.

---

## Monitoring & Alerting

| What to Monitor | How | Alert Channel |
|---|---|---|
| Azure Function execution | Function App → Monitor → Invocations | Application Insights |
| Function failures | App Insights alert rule on exception count | Email / Teams webhook |
| Power Automate flow failures | Flow run history + error handling scope | Email (built into each flow) |
| SharePoint folder — no files (dead man's switch) | Flow 3 (weekly digest) checks for empty folder | Email to admin DL |
| Data anomalies | Flow 4 (anomaly alert) | Email + Teams adaptive card |
| Secret expiration | Key Vault → Event Grid → expiration event | Email to admin |

---

## Disaster Recovery

| Scenario | Response |
|---|---|
| Azure Function fails silently | Flow 3's "no files this week" branch catches it within 7 days |
| Client secret expires | Key Vault expiration event alerts admin; rotate secret, update Key Vault |
| SharePoint site unavailable | Script's `run()` returns `status: "failed"` with error detail; Azure Function logs the failure; App Insights fires alert |
| Power BI dataset refresh fails | No new data to pull — row counts will match previous extract (no anomaly). Add a "data freshness" check: compare dataset last refresh time via PBI API |
| Power Automate flow breaks | Error handling scope sends notification; flow run history retains details |
| Someone manually drops a file in the folder | Flow 1/2 trigger on it — could send a false notification. Mitigate by filtering on filename prefix pattern |

---

## LLM Revision Guide

> **For an LLM modifying any part of this pipeline.**

### Document Map

- **This file** (`BHUNTER_PIPELINE_ARCHITECTURE.md`): Master reference. Update this when adding components or changing architecture.
- **`PBI_DATA_PULL_README.md`**: Script-specific docs. Update when modifying `pbi_data_pull.py`.
- **`BHUNTER_POWER_AUTOMATE_FLOWS.md`**: Flow specs. Update when adding/changing Power Automate flows.
- **`pbi_data_pull.py`**: The script. See its README for code structure and modification guide.

### Cross-Cutting Concerns

When modifying any component, check these cross-dependencies:

| If You Change... | Also Update... |
|---|---|
| `run()` return schema | All agent orchestration patterns in `PBI_DATA_PULL_README.md`; Flow 4 if it parses the result |
| `OUTPUT_FILENAME_PREFIX` | Flow 2 routing conditions |
| SharePoint folder path | Script config + all 4 flow triggers |
| Metadata sidecar schema | Flow 4 parse logic |
| Notification recipients | Distribution lists in Exchange (not in the flows directly) |
| Azure Function deployment | Key Vault references, App Insights config |
| Adding a new dataset | `TABLES` list in script + Flow 2 routing condition + recipient DL |

### Architecture Invariants (Do Not Break)

1. **Single-writer to SharePoint**: Only the Python script writes to `/PBI Extracts/`. Flows read only.
2. **`run()` never raises**: All errors caught internally, reported in the return dict. Agents depend on this.
3. **Metadata sidecar is JSON**: Flows parse it with `Parse JSON` action. Don't change format.
4. **Shared mailbox as sender**: Survives employee turnover. Don't switch to a personal account.
5. **Error handling scopes on every flow**: Non-negotiable. Silent failures in a data pipeline are unacceptable.
6. **Naming conventions**: Consistency across Azure resources, files, flows, and DLs. Follow the table above.
