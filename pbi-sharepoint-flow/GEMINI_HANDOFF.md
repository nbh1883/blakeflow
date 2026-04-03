# Gemini Project Handoff

This file is the starting point for an LLM helping finish this project.

If you are Gemini or another coding assistant, read this file first, then read:

1. `README.md`
2. `pbi-sharepoint-flow/pbi_data_pull.py`
3. `pbi-sharepoint-flow/BHUNTER_PIPELINE_ARCHITECTURE.md`
4. `pbi-sharepoint-flow/BHUNTER_POWER_AUTOMATE_FLOWS.md`

## What This Project Is

This repository is a mostly-complete blueprint for an automated Power BI to SharePoint pipeline.

The implemented code is a Python script that:

1. Authenticates to Azure AD / Entra ID with a service principal
2. Queries a published Power BI dataset using the Power BI REST API
3. Converts the returned tables into pandas DataFrames
4. Writes the results into an Excel workbook in memory
5. Optionally saves the workbook locally
6. Uploads the workbook to a SharePoint document library using Microsoft Graph
7. Returns a structured result dictionary for automation/orchestration

The repository also includes design docs for the larger system around that script:

- Power Automate notifications
- Routing by dataset/file prefix
- Weekly digest emails
- Anomaly detection using metadata sidecar JSON
- Azure Function deployment
- Key Vault secret storage

## What Already Exists

### Implemented now

- `pbi-sharepoint-flow/pbi_data_pull.py`
  - Main working script template
  - Contains `run()` entry point
  - Contains auth, Power BI query, Excel generation, and SharePoint upload logic

### Documentation already written

- `README.md`
  - Script setup and usage
  - Agent/orchestration patterns
  - Revision guidance

- `pbi-sharepoint-flow/BHUNTER_PIPELINE_ARCHITECTURE.md`
  - High-level architecture
  - Phased rollout plan
  - Security model
  - Monitoring guidance

- `pbi-sharepoint-flow/BHUNTER_POWER_AUTOMATE_FLOWS.md`
  - Four Power Automate flow designs
  - Trigger and action specs
  - Deployment checklist

## What Is Missing Or Still Placeholder

This project is not ready to deploy as-is. Several values and pieces are still placeholders or planned work.

### Missing configuration values

These values in `pbi-sharepoint-flow/pbi_data_pull.py` still need real values:

- `TENANT_ID`
- `CLIENT_ID`
- `CLIENT_SECRET`
- `DATASET_ID`
- `WORKSPACE_ID`
- `TABLES`
- `SHAREPOINT_SITE_URL`
- `SHAREPOINT_SITE_PATH`
- `SHAREPOINT_FOLDER`

### Placeholder company branding

The docs use placeholder names:

- `BHunter`
- `bhunter`
- `bhunter.com`

These should be replaced with the real company/client name, domain, mailbox names, DL names, Teams channel names, Azure resource names, and flow names.

### Not yet implemented in code

These are described in docs but are not fully implemented in the Python script yet:

- Environment variable or Key Vault based secret loading
- Metadata sidecar JSON upload for anomaly detection
- Azure Function wrapper files for scheduled/HTTP deployment
- Retry/backoff behavior around API calls
- Automated tests
- Power Automate flows themselves

### Maybe included elsewhere

There is a ZIP file:

- `pbi-sharepoint-flow/bhunter_pbi_pipeline.zip`

It may contain Power Automate exports or related artifacts, but this repository itself does not wire everything together automatically.

## What The LLM Should Do First

Do not immediately start rewriting the whole project.

First:

1. Read the files listed at the top of this handoff.
2. Summarize the current project state in plain English.
3. Identify what is implemented versus what is documentation only.
4. Ask the user for the missing deployment and business details listed below.
5. After receiving answers, propose a concrete completion plan.
6. Then implement the highest-value missing pieces in a safe order.

## Questions To Ask The User

Ask these questions in a concise, grouped way. These are the minimum details needed to finish the project correctly.

### Business context

1. What is the real company or client name that should replace `BHunter`?
2. What email domain should replace `bhunter.com`?
3. Who should receive notifications:
   - main data team
   - admin/failure alerts
   - any dataset-specific recipient groups
4. Will users rely on email, Teams, or both?

### Power BI details

5. What is the Power BI workspace ID?
6. What is the dataset ID?
7. Which exact table names should be extracted?
8. Is this for one dataset only, or multiple datasets?
9. Are there any large tables that need filtering or partitioning instead of full-table pulls?

### SharePoint details

10. What is the SharePoint host name, for example `contoso.sharepoint.com`?
11. What is the SharePoint site path, for example `/sites/DataTeam`?
12. What exact folder path should receive the uploads?
13. Should the script also save a local backup copy, or upload only?

### Azure / authentication details

14. Has an Entra ID app registration already been created?
15. If yes, what are the tenant ID, client ID, and how will the client secret be stored?
16. Should secrets live in environment variables, a `.env` file, or Azure Key Vault?
17. Will this run locally, in Azure Functions, or both?

### Automation details

18. Does the user want only the Python script finished, or the full pipeline including Power Automate flows?
19. Should Flow 1 only be built first, or should all four flows be prepared?
20. Is anomaly detection required now, or can it be deferred?
21. What schedule should the pipeline run on?

### Naming / operations

22. What filename prefix should be used for generated exports?
23. What should the Azure Function, Key Vault, app registration, and flow names be called?
24. Who will own and maintain the pipeline after delivery?

## Recommended Completion Order

Unless the user says otherwise, complete the project in this order:

1. Replace placeholder company/domain values in docs and config comments
2. Move secrets out of hardcoded constants into environment variables
3. Finalize `pbi_data_pull.py` configuration for the real dataset/site
4. Add metadata sidecar JSON generation and upload
5. Add a small Azure Function wrapper if cloud scheduling is required
6. Add basic error handling improvements and optional retry/backoff
7. Add simple tests or at least mocked validation paths
8. Build or document Power Automate Flow 1 first
9. Then build the other flows if still desired

## Important Constraints

When modifying this project, preserve these expectations:

1. `run()` should keep returning a structured dictionary and should not raise uncaught exceptions.
2. The Power BI and Graph scopes should remain valid for service principal auth.
3. The SharePoint upload should keep the simple PUT vs resumable upload split.
4. The docs assume the Python script is the single writer to the SharePoint extracts folder.
5. If the return schema changes, the docs and any orchestration examples must be updated too.

## Suggested First Response From Gemini

Use something close to this:

> I read the project and it looks like the Python extraction script is mostly scaffolded, while the Azure/SharePoint/Power Automate deployment details still need to be filled in with your real environment. I can help finish it, but first I need your real Power BI, SharePoint, Azure, and notification details. Please send the company name/domain, Power BI workspace ID, dataset ID, exact table names, SharePoint site/folder path, notification recipients, and whether you want local-only, Azure Function deployment, or the full Power Automate pipeline.

## Practical Goal

The goal is not just to "understand the repo." The goal is to help a non-technical or semi-technical owner finish deployment safely by:

- identifying the missing values
- asking for them clearly
- updating the code and docs with real values
- implementing only the next necessary pieces
- avoiding assumptions about production credentials or infrastructure

## If Information Is Missing

If the user does not know some IDs or paths, help them find them step by step:

- explain where to find Power BI workspace and dataset IDs
- explain how to verify table names
- explain how to identify the SharePoint site path and destination folder
- explain how to create or inspect the Entra app registration

Do not invent tenant IDs, dataset IDs, or recipient addresses.
