"""
Power BI Automated Data Pull → SharePoint
Authenticates via Service Principal, queries tables via PBI REST API,
exports to Excel, and uploads to a SharePoint document library via Graph API.

Designed to be called by an orchestration agent (Power Automate, Azure Function,
Semantic Kernel, etc.) or run standalone on a schedule.

Setup:
  1. Register an app in Azure AD (Entra ID) → grab Tenant ID, Client ID, Client Secret
  2. Grant it:
     - Power BI Service > Dataset.Read.All (Application)
     - Microsoft Graph > Sites.ReadWrite.All (Application) — for SharePoint upload
  3. Admin must grant consent for both permission sets
  4. Admin must enable "Allow service principals to use Power BI APIs" in PBI Admin Portal
  5. Add the service principal to the target PBI workspace (Viewer+)
  6. pip install msal requests openpyxl pandas
"""

import msal
import requests
import pandas as pd
import json
import sys
from datetime import datetime
from pathlib import Path
from io import BytesIO

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
TENANT_ID     = "YOUR_TENANT_ID"
CLIENT_ID     = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

# Power BI
DATASET_ID    = "YOUR_DATASET_ID"
WORKSPACE_ID  = "YOUR_WORKSPACE_ID"       # aka Group ID; None for "My Workspace"

TABLES = [
    "Sales",
    "Customers",
    "Products",
]

ROW_LIMIT = None  # e.g., 100000

# SharePoint
SHAREPOINT_SITE_URL  = "your-company.sharepoint.com"     # e.g., contoso.sharepoint.com
SHAREPOINT_SITE_PATH = "/sites/YourSiteName"             # e.g., /sites/DataTeam
SHAREPOINT_FOLDER    = "Shared Documents/PBI Extracts"   # folder path in the doc library

# Output
OUTPUT_FILENAME_PREFIX = "pbi_extract"
LOCAL_BACKUP = True   # keep a local copy alongside the SharePoint upload
LOCAL_DIR = Path("./output")

# ──────────────────────────────────────────────
# AUTH — dual-scope (PBI + Graph)
# ──────────────────────────────────────────────
class TokenManager:
    """Handles token acquisition for both Power BI and Microsoft Graph APIs."""

    PBI_SCOPE   = ["https://analysis.windows.net/powerbi/api/.default"]
    GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

    def __init__(self):
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        self.app = msal.ConfidentialClientApplication(
            CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
        )
        self._cache = {}

    def get_token(self, scope: list[str]) -> str:
        scope_key = scope[0]
        if scope_key not in self._cache:
            result = self.app.acquire_token_for_client(scopes=scope)
            if "access_token" not in result:
                raise Exception(f"Auth failed for {scope_key}: {result.get('error_description', result)}")
            self._cache[scope_key] = result["access_token"]
        return self._cache[scope_key]

    @property
    def pbi_token(self) -> str:
        return self.get_token(self.PBI_SCOPE)

    @property
    def graph_token(self) -> str:
        return self.get_token(self.GRAPH_SCOPE)

# ──────────────────────────────────────────────
# POWER BI QUERY
# ──────────────────────────────────────────────
def query_table(token: str, table_name: str) -> dict:
    if WORKSPACE_ID:
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/executeQueries"
    else:
        url = f"https://api.powerbi.com/v1.0/myorg/datasets/{DATASET_ID}/executeQueries"

    dax = f"EVALUATE '{table_name}'"
    if ROW_LIMIT:
        dax = f"EVALUATE TOPN({ROW_LIMIT}, '{table_name}')"

    body = {
        "queries": [{"query": dax}],
        "serializerSettings": {"includeNulls": True}
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.post(url, json=body, headers=headers, timeout=300)

    if resp.status_code != 200:
        return {"success": False, "table": table_name, "error": f"{resp.status_code}: {resp.text[:300]}"}

    rows = resp.json()["results"][0]["tables"][0]["rows"]
    if not rows:
        return {"success": True, "table": table_name, "rows": 0, "df": pd.DataFrame()}

    df = pd.DataFrame(rows)
    df.columns = [col.split("[")[-1].rstrip("]") if "[" in col else col for col in df.columns]

    return {"success": True, "table": table_name, "rows": len(df), "cols": len(df.columns), "df": df}

# ──────────────────────────────────────────────
# EXCEL EXPORT (in-memory buffer)
# ──────────────────────────────────────────────
def build_excel(table_data: dict[str, pd.DataFrame]) -> tuple[bytes, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_FILENAME_PREFIX}_{timestamp}.xlsx"

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for table_name, df in table_data.items():
            if df.empty:
                continue
            df.to_excel(writer, sheet_name=table_name[:31], index=False)

    return buffer.getvalue(), filename

# ──────────────────────────────────────────────
# SHAREPOINT UPLOAD (Graph API)
# ──────────────────────────────────────────────
def get_site_id(graph_token: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE_URL}:{SHAREPOINT_SITE_PATH}"
    headers = {"Authorization": f"Bearer {graph_token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Failed to resolve SharePoint site: {resp.status_code} — {resp.text[:300]}")
    return resp.json()["id"]

def get_drive_id(graph_token: str, site_id: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
    headers = {"Authorization": f"Bearer {graph_token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Failed to get drive: {resp.status_code} — {resp.text[:300]}")
    return resp.json()["id"]

def upload_to_sharepoint(graph_token: str, file_bytes: bytes, filename: str) -> dict:
    """
    Upload to SharePoint doc library via Graph API.
    Simple PUT for < 4MB, resumable upload session for larger files.
    """
    site_id = get_site_id(graph_token)
    drive_id = get_drive_id(graph_token, site_id)

    folder_encoded = SHAREPOINT_FOLDER.replace(" ", "%20")
    upload_path = f"{folder_encoded}/{filename}"
    headers = {"Authorization": f"Bearer {graph_token}"}
    file_size = len(file_bytes)

    if file_size < 4 * 1024 * 1024:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{upload_path}:/content"
        headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        resp = requests.put(url, data=file_bytes, headers=headers, timeout=60)
    else:
        session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{upload_path}:/createUploadSession"
        session_body = {"item": {"@microsoft.graph.conflictBehavior": "rename"}}
        session_resp = requests.post(session_url, json=session_body, headers=headers, timeout=30)
        if session_resp.status_code not in (200, 201):
            raise Exception(f"Upload session failed: {session_resp.status_code}")

        upload_url = session_resp.json()["uploadUrl"]
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        for start in range(0, file_size, chunk_size):
            end = min(start + chunk_size, file_size) - 1
            chunk = file_bytes[start:end + 1]
            chunk_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            }
            resp = requests.put(upload_url, data=chunk, headers=chunk_headers, timeout=120)

    if resp.status_code not in (200, 201):
        raise Exception(f"SharePoint upload failed: {resp.status_code} — {resp.text[:300]}")

    result = resp.json()
    return {
        "success": True,
        "filename": filename,
        "sharepoint_url": result.get("webUrl", ""),
        "size_bytes": file_size,
        "drive_item_id": result.get("id", ""),
    }

# ──────────────────────────────────────────────
# ORCHESTRATION ENTRY POINT
# ──────────────────────────────────────────────
def run(
    tables: list[str] | None = None,
    upload: bool = True,
    local_save: bool = LOCAL_BACKUP,
) -> dict:
    """
    Main entry point — designed to be called by an agent or orchestrator.

    Args:
        tables:     Override the default TABLES list. None uses config default.
        upload:     Whether to upload to SharePoint. False for local-only runs.
        local_save: Whether to also save a local copy.

    Returns:
        Structured result dict for agent consumption:
        {
            "status": "success" | "partial" | "failed",
            "tables_pulled": [...],
            "tables_failed": [...],
            "total_rows": int,
            "excel_filename": str,
            "sharepoint_url": str | None,
            "local_path": str | None,
            "errors": [...]
        }
    """
    result = {
        "status": "failed",
        "tables_pulled": [],
        "tables_failed": [],
        "total_rows": 0,
        "excel_filename": None,
        "sharepoint_url": None,
        "local_path": None,
        "errors": [],
    }

    target_tables = tables or TABLES

    # Auth
    try:
        tokens = TokenManager()
        _ = tokens.pbi_token
        if upload:
            _ = tokens.graph_token
    except Exception as e:
        result["errors"].append(f"Auth failed: {e}")
        return result

    # Query tables
    table_data = {}
    for table in target_tables:
        qr = query_table(tokens.pbi_token, table)
        if not qr.get("success", False):
            result["tables_failed"].append(table)
            result["errors"].append(qr.get("error", f"Unknown error on {table}"))
        else:
            df = qr["df"]
            table_data[table] = df
            result["tables_pulled"].append({"table": table, "rows": len(df)})
            result["total_rows"] += len(df)

    if not table_data:
        result["errors"].append("No tables returned data")
        return result

    # Build Excel (in-memory)
    try:
        file_bytes, filename = build_excel(table_data)
        result["excel_filename"] = filename
    except Exception as e:
        result["errors"].append(f"Excel build failed: {e}")
        return result

    # Local save
    if local_save:
        try:
            LOCAL_DIR.mkdir(exist_ok=True)
            local_path = LOCAL_DIR / filename
            local_path.write_bytes(file_bytes)
            result["local_path"] = str(local_path)
        except Exception as e:
            result["errors"].append(f"Local save failed: {e}")

    # SharePoint upload
    if upload:
        try:
            sp_result = upload_to_sharepoint(tokens.graph_token, file_bytes, filename)
            result["sharepoint_url"] = sp_result["sharepoint_url"]
        except Exception as e:
            result["errors"].append(f"SharePoint upload failed: {e}")

    # Final status
    if result["tables_failed"]:
        result["status"] = "partial"
    elif result["sharepoint_url"] or not upload:
        result["status"] = "success"

    return result

# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def main():
    print("── Power BI Data Pull → SharePoint ──\n")
    result = run()
    print(json.dumps(result, indent=2, default=str))
    if result["status"] == "failed":
        sys.exit(1)
    return result


if __name__ == "__main__":
    main()
