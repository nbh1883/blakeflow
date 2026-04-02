# BHunter — Power Automate Flow Specifications

> **⚠️ "BHunter" is a placeholder company name.** Before deploying, find-and-replace all instances of `BHunter`, `bhunter`, and `bhunter.com` with your actual company name and domain across all flow definitions, email addresses, Teams references, and connection names.

## Overview

This document defines the Power Automate flows that sit on top of the PBI data extraction pipeline. The Python script (`pbi_data_pull.py`) handles the data pull and SharePoint upload. Power Automate handles everything downstream: notifications, routing, anomaly alerts, digest emails, and approval workflows.

There are four flows defined here, ordered by implementation priority.

---

## Flow 1: File Drop Notification

**Priority:** Implement first — immediate value, minimal setup.

**Trigger:** When a file is created in a folder (SharePoint)

**Purpose:** Notify stakeholders when a new PBI extract lands in SharePoint. Includes a direct link to the file and a metadata summary (file size, table count, timestamp).

### Flow Definition

```
TRIGGER: When a file is created in a folder
  Site:   BHunter SharePoint
  Folder: /Shared Documents/PBI Extracts

ACTION 1: Get file properties
  Site:    BHunter SharePoint
  Library: Shared Documents
  Id:      [trigger file ID]

ACTION 2: Compose — Build metadata
  Inputs:
    {
      "filename": @{triggerOutputs()?['body/{Name}']},
      "size_mb": @{div(triggerOutputs()?['body/{Size}'], 1048576)},
      "created": @{formatDateTime(triggerOutputs()?['body/{TimeCreated}'], 'MMM dd, yyyy h:mm tt')},
      "link": @{triggerOutputs()?['body/{Link}']}
    }

ACTION 3: Send an email (V2) — Office 365 Outlook
  To:       bhunter-data-team@bhunter.com  (or DL / specific recipients)
  Subject:  PBI Extract Available — @{outputs('Compose')?['filename']}
  Body (HTML):
    <h2>New PBI Data Extract</h2>
    <table>
      <tr><td><b>File</b></td><td>@{outputs('Compose')?['filename']}</td></tr>
      <tr><td><b>Size</b></td><td>@{outputs('Compose')?['size_mb']} MB</td></tr>
      <tr><td><b>Uploaded</b></td><td>@{outputs('Compose')?['created']}</td></tr>
    </table>
    <br>
    <a href="@{outputs('Compose')?['link']}">Open in SharePoint</a>
    <br><br>
    <p style="color:#666;font-size:12px;">
      Automated by BHunter Data Pipeline. Do not reply to this email.
    </p>
  Importance: Normal

ACTION 4 (Optional): Post message in a chat or channel — Microsoft Teams
  Team:    BHunter Data Team
  Channel: #data-alerts
  Message:
    📊 **New PBI Extract:** @{outputs('Compose')?['filename']}
    Size: @{outputs('Compose')?['size_mb']} MB | [Open file](@{outputs('Compose')?['link']})
```

### Notes

- The distribution list (`bhunter-data-team@bhunter.com`) should be managed in Exchange/Entra ID so you don't hardcode individual emails.
- The Teams post is optional — use it if the team lives in Teams; skip if email-only culture.
- If the extract cadence is daily, consider suppressing the email and only using Teams to avoid inbox fatigue.

---

## Flow 2: Conditional Routing by Dataset

**Priority:** Implement after Flow 1 — adds targeting so the right people get the right files.

**Trigger:** When a file is created in a folder (SharePoint)

**Purpose:** Route notifications to different recipients based on which dataset/report the extract came from. The Python script names files with a configurable prefix (`OUTPUT_FILENAME_PREFIX`), so you can use filename pattern matching to route.

### Flow Definition

```
TRIGGER: When a file is created in a folder
  Site:   BHunter SharePoint
  Folder: /Shared Documents/PBI Extracts

ACTION 1: Initialize variable — recipientGroup
  Name: recipientGroup
  Type: String
  Value: ""

ACTION 2: Initialize variable — datasetLabel
  Name: datasetLabel
  Type: String
  Value: "General"

CONDITION 1: Check filename prefix
  If: contains(triggerOutputs()?['body/{Name}'], 'sales_extract')
  Yes →
    Set variable: recipientGroup = "sales-team@bhunter.com"
    Set variable: datasetLabel = "Sales"
  No →

    CONDITION 2:
    If: contains(triggerOutputs()?['body/{Name}'], 'finance_extract')
    Yes →
      Set variable: recipientGroup = "finance-team@bhunter.com"
      Set variable: datasetLabel = "Finance"
    No →
      Set variable: recipientGroup = "bhunter-data-team@bhunter.com"
      Set variable: datasetLabel = "General"

ACTION 3: Send an email (V2)
  To:      @{variables('recipientGroup')}
  Subject: @{variables('datasetLabel')} PBI Extract — @{triggerOutputs()?['body/{Name}']}
  Body:    [same HTML template as Flow 1, with datasetLabel added]

ACTION 4 (Optional): Post to dataset-specific Teams channel
  Channel: determined by datasetLabel
```

### Configuration Pattern

To make this work cleanly, set `OUTPUT_FILENAME_PREFIX` in the Python script per dataset:

```python
# For the sales pipeline run
OUTPUT_FILENAME_PREFIX = "sales_extract"

# For the finance pipeline run
OUTPUT_FILENAME_PREFIX = "finance_extract"
```

Or better — pass it dynamically via the `run()` function (minor script modification: add a `filename_prefix` param).

### Notes

- If you have more than 3–4 routing conditions, switch from nested conditions to a **Switch** action on a parsed prefix string — cleaner and easier to maintain.
- Consider a SharePoint list as a routing config table: columns for `prefix`, `recipients`, `teams_channel`. The flow reads the list and routes dynamically — no flow edits needed when routing changes.

---

## Flow 3: Weekly Digest Email

**Priority:** Implement when daily notifications become noise.

**Trigger:** Recurrence — Weekly (e.g., Monday 8:00 AM)

**Purpose:** Instead of notifying per-file, collect all extracts from the past week and send a single digest email with a summary table and links.

### Flow Definition

```
TRIGGER: Recurrence
  Frequency: Week
  Interval:  1
  Day:       Monday
  Time:      08:00 AM
  Time Zone: Central Time (US & Canada)

ACTION 1: Get files (properties only) — SharePoint
  Site:    BHunter SharePoint
  Library: Shared Documents
  Folder:  /PBI Extracts
  Filter:  TimeCreated ge '@{addDays(utcNow(), -7)}'
  Top:     50

ACTION 2: Select — Map to summary rows
  From: @{outputs('Get_files')?['body/value']}
  Map:
    {
      "filename": @{item()?['Name']},
      "size_mb": @{div(item()?['Size'], 1048576)},
      "created": @{formatDateTime(item()?['TimeCreated'], 'MMM dd h:mm tt')},
      "link": @{item()?['Link']}
    }

ACTION 3: Create HTML table
  From:    @{body('Select')}
  Columns: Automatic
  (or Custom with headers: File, Size (MB), Uploaded, Link)

ACTION 4: Compose — File count
  Inputs: @{length(outputs('Get_files')?['body/value'])}

CONDITION: If file count > 0
  Yes →
    ACTION 5: Send an email (V2)
      To:      bhunter-data-team@bhunter.com
      Subject: BHunter Weekly Data Digest — @{outputs('Compose')} extracts
      Body (HTML):
        <h2>Weekly PBI Extract Digest</h2>
        <p>@{outputs('Compose')} files were uploaded to SharePoint this week.</p>
        @{body('Create_HTML_table')}
        <br>
        <a href="[SharePoint folder URL]">Browse all extracts</a>
        <br><br>
        <p style="color:#666;font-size:12px;">
          Week of @{formatDateTime(addDays(utcNow(), -7), 'MMM dd')} – @{formatDateTime(utcNow(), 'MMM dd, yyyy')}
        </p>

  No →
    ACTION 6: Send an email (V2)
      To:      bhunter-data-admin@bhunter.com
      Subject: ⚠️ No PBI extracts this week
      Body:    No files were uploaded to the PBI Extracts folder in the past 7 days.
               This may indicate a pipeline failure. Check Azure Function logs.
```

### Notes

- The "no files" branch is critical — it's your dead man's switch. If the pipeline silently breaks, this catches it.
- The HTML table action produces a basic table. For a polished look, use a Compose action to build custom HTML with inline CSS instead.
- If you want to include row counts per file, the Python script would need to write a metadata sidecar file (e.g., `pbi_extract_20260323.json` alongside the `.xlsx`) that the flow reads.

---

## Flow 4: Anomaly Alert (Requires Metadata Sidecar)

**Priority:** Phase 2 — adds intelligence. Requires a small script modification.

**Trigger:** When a file is created in a folder (SharePoint) — filtered to `.json` metadata files

**Purpose:** Compare the current extract's row counts to the previous extract. If any table's row count changed by more than a configurable threshold (e.g., ±20%), fire an alert.

### Script Modification Required

Add a metadata sidecar export to `run()` — after `build_excel`, write a `.json` file alongside:

```python
# Add to run(), after build_excel succeeds
metadata = {
    "filename": filename,
    "timestamp": datetime.now().isoformat(),
    "tables": {t["table"]: t["rows"] for t in result["tables_pulled"]},
    "total_rows": result["total_rows"],
}
metadata_filename = filename.replace(".xlsx", "_meta.json")
# Upload metadata JSON to SharePoint alongside the Excel
```

### Flow Definition

```
TRIGGER: When a file is created in a folder
  Site:   BHunter SharePoint
  Folder: /Shared Documents/PBI Extracts
  Filter: endswith(Name, '_meta.json')

ACTION 1: Get file content — Current metadata
  File: [trigger file ID]
  → Parse JSON

ACTION 2: Get files (properties only) — Find previous metadata
  Library: Shared Documents
  Folder:  /PBI Extracts
  Filter:  endswith(Name, '_meta.json') and TimeCreated lt '@{triggerOutputs()?['body/{TimeCreated}']}'
  Order:   TimeCreated desc
  Top:     1

CONDITION: If previous metadata exists
  Yes →
    ACTION 3: Get file content — Previous metadata
      → Parse JSON

    ACTION 4: Apply to each — Compare table row counts
      Input: @{body('Parse_JSON_current')?['tables']}

      For each table:
        current_rows  = current[table]
        previous_rows = previous[table]
        pct_change    = abs((current - previous) / previous) * 100

        CONDITION: If pct_change > 20
          Yes →
            Append to array variable: anomalies
              {
                "table": table_name,
                "previous": previous_rows,
                "current": current_rows,
                "change_pct": pct_change
              }

    CONDITION: If anomalies array is not empty
      Yes →
        ACTION 5: Send an email (V2)
          To:      bhunter-data-admin@bhunter.com
          Subject: ⚠️ Data Anomaly Detected — @{length(variables('anomalies'))} tables flagged
          Body:
            <h2>Anomaly Alert</h2>
            <p>The following tables had row count changes exceeding 20%:</p>
            [HTML table of anomalies]
            <p>Current extract: @{body('Parse_JSON_current')?['filename']}</p>
            <a href="[file link]">Open in SharePoint</a>

        ACTION 6: Post adaptive card in Teams
          Team:    BHunter Data Team
          Channel: #data-alerts
          Card:    [Adaptive card with anomaly summary + action buttons]
```

### Notes

- The 20% threshold is a starting point. Make it configurable via a SharePoint list or environment variable.
- For tables that are append-only (e.g., transaction logs), row count should only go up. A decrease is always an anomaly. You could add directional logic: flag any decrease, but only flag increases above threshold.
- The Adaptive Card in Teams can include action buttons: "Acknowledge", "Investigate", "Ignore" — feeding back into a tracking list.

---

## Shared Configuration: Connection References

All four flows share the same connectors. Set up connection references so credentials are managed centrally:

| Connector | Connection Reference Name | Auth |
|---|---|---|
| SharePoint | `BHunter-SharePoint-Conn` | Service account or delegated |
| Office 365 Outlook | `BHunter-Outlook-Conn` | Service account (shared mailbox recommended) |
| Microsoft Teams | `BHunter-Teams-Conn` | Service account or delegated |

Use a **shared mailbox** (e.g., `datapipeline@bhunter.com`) as the email sender so notifications don't come from an individual's inbox.

---

## Error Handling Pattern (Apply to All Flows)

Wrap the core logic in a **Scope** action and add a parallel **Scope** for error handling:

```
SCOPE: Main Logic
  [all flow actions]
  Configure run after: Succeeded

SCOPE: Error Handler (parallel branch)
  Configure run after: Failed, Timed Out
  ACTION: Send an email
    To:      bhunter-data-admin@bhunter.com
    Subject: ❌ Flow Failed: [flow name]
    Body:    Error details from workflow() expression
  ACTION: Post to Teams #data-alerts
    Message: Flow failure notification
```

This ensures you always get notified if a flow itself breaks — not just if the data pipeline breaks.

---

## Deployment Checklist

1. [ ] Create shared mailbox `datapipeline@bhunter.com` (or equivalent)
2. [ ] Create SharePoint folder structure: `/Shared Documents/PBI Extracts/`
3. [ ] Create distribution lists: `bhunter-data-team`, `bhunter-data-admin`, and any dataset-specific DLs
4. [ ] Create Teams channel: `#data-alerts` in the appropriate Team
5. [ ] Set up connection references in Power Automate environment
6. [ ] Deploy Flow 1 (file drop notification) — test with a manual file upload
7. [ ] Deploy Flow 2 (conditional routing) — test with different filename prefixes
8. [ ] Deploy Flow 3 (weekly digest) — test by manually triggering
9. [ ] Modify Python script for metadata sidecar (Flow 4 prerequisite)
10. [ ] Deploy Flow 4 (anomaly alert) — test with synthetic anomaly data
11. [ ] Document all flow URLs and owner assignments in a shared location
12. [ ] Set up monitoring: Power Automate analytics + flow run history alerts

---

## LLM Revision Guide

> **For an LLM modifying these flows or building them out in Power Automate.**

### Flow Architecture Principles

- All flows trigger from SharePoint file events — the Python script is the **only** thing that writes to the PBI Extracts folder. This is a deliberate single-writer pattern.
- Notifications go through a shared mailbox, not individual accounts. This survives employee turnover.
- Error handling scopes are mandatory on every flow. Silent failures are unacceptable in a data pipeline.
- The metadata sidecar pattern (Flow 4) is the bridge between "dumb file drop" and "intelligent pipeline." Any future agent capabilities should read the sidecar, not parse the Excel.

### Common Modification Requests

| Request | What to Change |
|---|---|
| "Add a new recipient" | Update the distribution list in Exchange — no flow change needed |
| "Route to a new team" | Flow 2: add a condition branch, or add a row to the routing config SharePoint list |
| "Change digest frequency" | Flow 3: update the Recurrence trigger (daily, biweekly, etc.) |
| "Lower anomaly threshold" | Flow 4: change the 20% comparison value |
| "Add Slack instead of Teams" | Replace the Teams connector with the Slack connector — same message content |
| "Add approval before email" | Insert an Approval action between the trigger and the email send |
| "Add file archival" | After notification, add a "Move file" action to an `/Archive/YYYY-MM/` folder |
| "Notify on pipeline failure" | The Python `run()` returns `status: "failed"` — if called via HTTP trigger Azure Function, Power Automate reads the response and branches on status |

### Things Not to Change

1. **Single-writer pattern** — only the Python script writes to the PBI Extracts folder. If humans start manually dropping files there, Flow 2's routing logic breaks.
2. **Shared mailbox as sender** — switching to a personal account creates a single point of failure.
3. **Error handling scopes** — removing them saves zero effort and creates blind spots.
4. **Metadata sidecar as JSON** — don't switch to CSV or embed metadata in the Excel. JSON is machine-readable, schema-flexible, and the flows parse it natively.
