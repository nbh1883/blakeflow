# Power BI Automated Data Pull → SharePoint

> **Part of the BHunter Data Pipeline.** This doc covers the Python script only. See also:
> - `BHUNTER_PIPELINE_ARCHITECTURE.md` — master architecture, phased rollout, security model, monitoring
> - `BHUNTER_POWER_AUTOMATE_FLOWS.md` — 4 Power Automate flow specs (notification, routing, digest, anomaly)
>
> **⚠️ "BHunter" is a placeholder company name.** Find-and-replace `BHunter`, `bhunter`, and `bhunter.com` with your actual company name and domain before deploying.

## What This Is

A Python script (`pbi_data_pull.py`) that:

1. Authenticates against Azure AD via a Service Principal
2. Runs DAX queries against a published Power BI dataset (REST API)
3. Builds an Excel workbook in memory (one sheet per table)
4. Uploads the workbook to a SharePoint document library (Graph API)
5. Returns a structured JSON result for agent/orchestrator consumption

The script exposes a `run()` function designed to be called programmatically by an orchestration agent (Semantic Kernel, AutoGen, LangChain, Power Automate, Azure Functions) or run standalone via CLI.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│            ORCHESTRATION LAYER                  │
│  (Semantic Kernel / AutoGen / Power Automate /  │
│   Azure Function / cron / CLI)                  │
└──────────────────┬──────────────────────────────┘
                   │  calls run()
                   ▼
┌─────────────────────────────────────────────────┐
│              pbi_data_pull.py                    │
│                                                 │
│  TokenManager (MSAL)                            │
│    ├─ PBI token  ──→  executeQueries endpoint   │
│    └─ Graph token ──→  SharePoint upload         │
│                                                 │
│  query_table()   → DAX → JSON → DataFrame       │
│  build_excel()   → DataFrames → bytes (in-mem)  │
│  upload_to_sharepoint() → Graph API PUT/chunked │
│                                                 │
│  Returns: structured result dict (JSON)          │
└─────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
   SharePoint                 Local backup
   Document Library            ./output/
```

---

## Prerequisites

### Python Packages

```bash
pip install msal requests openpyxl pandas
```

Tested on Python 3.10+. No version-specific features; should work on 3.8+.

### Azure AD / Entra ID Setup

**Step 1: Register an App**

1. Azure Portal → [App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) → **New registration**
2. Name: `PBI-DataPull-Automation` (or similar)
3. Supported account types: "Accounts in this organizational directory only"
4. No redirect URI needed
5. Note the **Application (client) ID** and **Directory (tenant) ID**

**Step 2: Create a Client Secret**

1. App registration → **Certificates & secrets** → **New client secret**
2. Set expiration (12–24 months recommended; set a calendar reminder to rotate)
3. Copy the **Value** immediately — it's only shown once

**Step 3: Grant API Permissions**

Two permission sets are required:

| API | Permission | Type | Purpose |
|-----|-----------|------|---------|
| Power BI Service | `Dataset.Read.All` | Application | Query datasets via executeQueries |
| Microsoft Graph | `Sites.ReadWrite.All` | Application | Upload files to SharePoint |

After adding both, click **Grant admin consent** (requires Global Admin or Privileged Role Admin).

**Step 4: Enable Service Principals in Power BI**

1. [Power BI Admin Portal](https://app.powerbi.com/admin-portal/tenantSettings) → Developer settings
2. Enable **"Allow service principals to use Power BI APIs"**
3. Scope to a security group containing your SP (recommended over tenant-wide)

**Step 5: Add SP to PBI Workspace**

1. Power BI Service → target workspace → **Access**
2. Add the app (search by name or client ID)
3. Assign **Viewer** role minimum

---

## Configuration

All config is at the top of `pbi_data_pull.py`:

### Authentication

| Variable | Description | Source |
|---|---|---|
| `TENANT_ID` | Azure AD directory ID | Azure Portal → App Registration → Overview |
| `CLIENT_ID` | Application (client) ID | Azure Portal → App Registration → Overview |
| `CLIENT_SECRET` | Secret value | Azure Portal → Certificates & secrets |

### Power BI

| Variable | Description | Source |
|---|---|---|
| `DATASET_ID` | Power BI dataset GUID | PBI Service URL: `datasets/{datasetId}` |
| `WORKSPACE_ID` | Workspace/group GUID | PBI Service URL: `groups/{workspaceId}` — `None` for "My Workspace" |
| `TABLES` | List of table names to extract | Must match semantic model names exactly (case-sensitive) |
| `ROW_LIMIT` | Max rows per table | `None` for unlimited |

### SharePoint

| Variable | Description | Example |
|---|---|---|
| `SHAREPOINT_SITE_URL` | Root SharePoint domain | `contoso.sharepoint.com` |
| `SHAREPOINT_SITE_PATH` | Site path | `/sites/DataTeam` |
| `SHAREPOINT_FOLDER` | Folder in the document library | `Shared Documents/PBI Extracts` |

The folder must already exist in SharePoint. The script does not create folders.

### Finding IDs

**Dataset ID / Workspace ID** — from any report URL in PBI Service:

```
https://app.powerbi.com/groups/{WORKSPACE_ID}/reports/{reportId}
https://app.powerbi.com/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/details
```

**Table names** — find via:

- Power BI Desktop → Model view → table list
- DAX Studio → `SELECT * FROM $SYSTEM.TMSCHEMA_TABLES`
- Tabular Editor → table names

**SharePoint site path** — from the site URL:

```
https://contoso.sharepoint.com/sites/DataTeam → site path is /sites/DataTeam
```

---

## Usage

### CLI (standalone)

```bash
python pbi_data_pull.py
```

Outputs a JSON result to stdout and writes the Excel to `./output/` (if `LOCAL_BACKUP = True`) plus SharePoint.

### Programmatic (agent/orchestrator)

```python
from pbi_data_pull import run

# Default config
result = run()

# Override tables, skip SharePoint (local only)
result = run(tables=["Sales", "Inventory"], upload=False)

# Upload only, no local copy
result = run(local_save=False)
```

### Return Schema

Every call to `run()` returns a dict:

```json
{
    "status": "success | partial | failed",
    "tables_pulled": [
        {"table": "Sales", "rows": 45000},
        {"table": "Customers", "rows": 1200}
    ],
    "tables_failed": [],
    "total_rows": 46200,
    "excel_filename": "pbi_extract_20260323_060000.xlsx",
    "sharepoint_url": "https://contoso.sharepoint.com/sites/DataTeam/Shared%20Documents/PBI%20Extracts/pbi_extract_20260323_060000.xlsx",
    "local_path": "./output/pbi_extract_20260323_060000.xlsx",
    "errors": []
}
```

| Status | Meaning |
|---|---|
| `success` | All tables pulled, upload succeeded |
| `partial` | Some tables failed, rest succeeded |
| `failed` | Auth failed, no data returned, or Excel build failed |

---

## Agent Orchestration Patterns

### Pattern 1: Semantic Kernel (Python)

```python
import semantic_kernel as sk
from semantic_kernel.functions import kernel_function

class PBIDataPlugin:
    @kernel_function(description="Pull Power BI data and upload to SharePoint")
    def pull_pbi_data(self, tables: str = "") -> str:
        from pbi_data_pull import run
        table_list = [t.strip() for t in tables.split(",")] if tables else None
        result = run(tables=table_list)
        return json.dumps(result)

kernel = sk.Kernel()
kernel.add_plugin(PBIDataPlugin(), "pbi")
```

The agent can then be prompted: *"Pull the Sales and Customers tables from Power BI and upload to SharePoint."* The structured return lets the agent reason about success/failure and take follow-up actions (retry, notify, etc.).

### Pattern 2: AutoGen

```python
from autogen import AssistantAgent, UserProxyAgent

def pbi_pull_tool(tables: list[str] | None = None) -> dict:
    from pbi_data_pull import run
    return run(tables=tables)

assistant = AssistantAgent("data_agent", ...)
user_proxy = UserProxyAgent("user", ...)
user_proxy.register_function(function_map={"pbi_pull": pbi_pull_tool})
```

### Pattern 3: Azure Function (Timer Trigger)

```python
# function_app.py
import azure.functions as func
import logging
from pbi_data_pull import run

app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 6 * * *", arg_name="timer")  # daily at 6 AM UTC
def pbi_scheduled_pull(timer: func.TimerRequest):
    result = run()
    logging.info(f"PBI pull: {result['status']} — {result['total_rows']} rows")
    if result["status"] == "failed":
        # trigger alert (email, Teams webhook, PagerDuty, etc.)
        raise Exception(f"PBI pull failed: {result['errors']}")
```

For Azure Functions, move secrets to **Azure Key Vault** and reference them via app settings:

```python
import os
TENANT_ID     = os.environ["PBI_TENANT_ID"]
CLIENT_ID     = os.environ["PBI_CLIENT_ID"]
CLIENT_SECRET = os.environ["PBI_CLIENT_SECRET"]
```

### Pattern 4: Power Automate (HTTP action)

If the script is deployed as an Azure Function with an HTTP trigger, Power Automate can call it via the **HTTP** action:

1. Create a cloud flow with a **Recurrence** trigger
2. Add an **HTTP** action pointing to the Azure Function URL
3. Parse the JSON response
4. Add a **Condition** on `status` — if `failed`, send a Teams/email notification

This is the lowest-code option and keeps the Python logic server-side while the orchestration lives in Power Automate.

### Pattern 5: LangChain Tool

```python
from langchain.tools import tool

@tool
def pull_pbi_data(tables: str = "") -> str:
    """Pull data from Power BI dataset and upload to SharePoint.
    Args: tables — comma-separated table names, or empty for defaults."""
    from pbi_data_pull import run
    table_list = [t.strip() for t in tables.split(",")] if tables else None
    return json.dumps(run(tables=table_list))
```

---

## Known Constraints and Gotchas

### API Row Limit

`executeQueries` caps at ~1,000,000 rows per query. Partition large tables:

```python
years = [2022, 2023, 2024, 2025]
frames = []
for y in years:
    dax = f"EVALUATE FILTER('Sales', YEAR('Sales'[OrderDate]) = {y})"
    # run custom DAX query and collect frames
```

### Rate Limits

~200 requests/hour per service principal. Fine for a handful of tables; add backoff if scaling to 50+ tables or parallel runs.

### SharePoint Folder Must Exist

The script does not create the target folder. Create it manually in SharePoint before the first run, or add a Graph API `PATCH` call to create it programmatically.

### File Size and Upload Method

- Files < 4MB → simple PUT (fast, single request)
- Files ≥ 4MB → resumable upload session with 10MB chunks
- Graph API max file size via upload session: 250GB (not a practical concern here)

### Token Lifetime

MSAL client credentials tokens last ~60–90 minutes. If extraction somehow takes longer, you'd need mid-run token refresh. The `TokenManager` class caches tokens but doesn't refresh — add a TTL check if needed.

### Column Name Collisions

The API returns `TableName[ColumnName]` format. The script strips to `ColumnName`. If two tables share column names and you merge them downstream, handle deduplication at that point.

### Client Secret Rotation

Secrets expire. Calendar-reminder the expiration. Rotate: create new secret → update config/Key Vault → test → delete old secret.

---

## Security Recommendations

1. **Never commit secrets to source control.** Use environment variables, `.env` (gitignored), or Azure Key Vault.
2. **Scope the SP narrowly.** Viewer on specific workspace(s) only. `Sites.ReadWrite.All` is broad — if you can scope to `Sites.Selected`, do so (requires Graph app consent configuration per-site).
3. **Use a security group** for the PBI admin tenant setting.
4. **Audit via Azure AD sign-in logs.**

### Environment Variable Pattern

```python
import os
TENANT_ID     = os.environ["PBI_TENANT_ID"]
CLIENT_ID     = os.environ["PBI_CLIENT_ID"]
CLIENT_SECRET = os.environ["PBI_CLIENT_SECRET"]
```

---

## LLM Revision Guide

> **This section is for an LLM (Claude, GPT, etc.) that will modify this script. Read before making changes.**

### Code Structure

| Function / Class | Purpose | Notes |
|---|---|---|
| `TokenManager` | MSAL auth for PBI + Graph scopes | Caches tokens in `_cache` dict. Two scopes, two tokens. |
| `query_table(token, table)` | DAX query → DataFrame | Returns a dict with `success`, `df`, `rows`, `error`. |
| `build_excel(table_data)` | DataFrames → Excel bytes in memory | Returns `(bytes, filename)`. Uses `BytesIO` — no disk write. |
| `get_site_id(token)` | Resolves SharePoint site URL → site ID | Graph API call. |
| `get_drive_id(token, site_id)` | Gets default document library drive ID | Graph API call. |
| `upload_to_sharepoint(token, bytes, filename)` | PUT or chunked upload to SharePoint | Switches method based on file size (4MB threshold). |
| `run(tables, upload, local_save)` | **Main entry point.** Orchestrators call this. | Returns structured result dict. All error handling is here. |
| `main()` | CLI wrapper around `run()`. | Prints JSON, exits with code 1 on failure. |

### Return Contract

`run()` always returns a dict with these keys — never raises. All exceptions are caught and appended to `errors[]`. Orchestration agents depend on this contract.

```python
{
    "status": str,           # "success" | "partial" | "failed"
    "tables_pulled": list,   # [{"table": str, "rows": int}, ...]
    "tables_failed": list,   # [str, ...]
    "total_rows": int,
    "excel_filename": str | None,
    "sharepoint_url": str | None,
    "local_path": str | None,
    "errors": list[str],
}
```

**Do not change this schema without updating all orchestration patterns in this README.** Agents parse these keys.

### Common Modification Requests

| Request | What to Change |
|---|---|
| "Add a new table" | Add string to `TABLES` list |
| "Use env vars for secrets" | Replace hardcoded strings with `os.environ[...]` |
| "Output CSV instead of Excel" | Replace `build_excel` to write CSVs; update `upload_to_sharepoint` content type |
| "Custom DAX instead of full tables" | Add `custom_dax` param to `query_table`; skip the auto-generated `EVALUATE` when provided |
| "Add retry/backoff" | Wrap `requests.post` in `query_table` with exponential backoff loop |
| "Pull from multiple datasets" | Refactor `run()` to accept a list of dataset configs; loop and merge results |
| "Add Teams/Slack notification" | Add a `notify()` function called at end of `run()` based on status |
| "Change upload to different SharePoint site" | Update the three `SHAREPOINT_*` config vars |
| "Upload to a subfolder by date" | Modify `SHAREPOINT_FOLDER` dynamically: `f"Shared Documents/PBI Extracts/{datetime.now():%Y-%m}"` |
| "Add incremental/delta pull" | Add date filter to DAX based on a watermark file (last pull timestamp) |
| "Deploy as Azure Function" | Wrap `run()` in a timer or HTTP trigger; move secrets to Key Vault |

### Things NOT to Change Without Good Reason

1. **MSAL scopes** — `https://analysis.windows.net/powerbi/api/.default` (PBI) and `https://graph.microsoft.com/.default` (Graph) are the only valid scopes for client credentials.
2. **`serializerSettings.includeNulls: true`** — without this, rows with nulls silently drop keys, causing misaligned DataFrames.
3. **Column name cleaning** — `TableName[Column]` → `Column` is mandatory for usable DataFrames.
4. **`run()` return schema** — agents depend on the exact keys. Add keys if needed; never remove or rename.
5. **The 4MB upload threshold** — this is a Graph API hard limit for simple PUT uploads. The chunked upload path handles larger files.
6. **`BytesIO` in-memory buffer pattern** — writing to disk then reading back is wasteful; the buffer is passed directly to both local save and upload.

### API References

- **PBI executeQueries**: `POST /v1.0/myorg/groups/{groupId}/datasets/{datasetId}/executeQueries` — [Docs](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries)
- **Graph site resolution**: `GET /v1.0/sites/{host}:{path}` — [Docs](https://learn.microsoft.com/en-us/graph/api/site-getbypath)
- **Graph file upload (simple)**: `PUT /v1.0/drives/{driveId}/root:/{path}:/content` — [Docs](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content)
- **Graph file upload (resumable)**: `POST .../createUploadSession` — [Docs](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession)

### Testing Without Live Environment

1. Mock `requests.post`/`requests.put`/`requests.get` responses matching the schemas above
2. Verify column name cleaning handles edge cases (`]` in names, single-word tables)
3. Verify `build_excel` produces a valid .xlsx from sample DataFrames
4. Verify `run()` returns correct status for all scenarios: all succeed, some fail, all fail, auth fails
5. Verify chunked upload logic with a buffer > 4MB

### Dependencies

| Package | Min Version | Notes |
|---|---|---|
| `msal` | 1.20+ | Client credentials flow |
| `requests` | 2.25+ | Standard HTTP |
| `pandas` | 1.3+ | `ExcelWriter` with openpyxl engine |
| `openpyxl` | 3.0+ | Excel engine (transitive via pandas) |

**requirements.txt:**

```
msal>=1.20.0
requests>=2.25.0
pandas>=1.3.0
openpyxl>=3.0.0
```
