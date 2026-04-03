# Start Here

This folder contains a project for automating a Power BI data export to SharePoint, with optional notifications and other automation around it.

If you are opening this in Gemini, ChatGPT, or another coding assistant, start with this prompt:

> Read `GEMINI_HANDOFF.md` first, then read the referenced files, explain what is already built vs what is still missing, and ask me for the exact details you need to finish the project safely.

## What To Expect

The project is partly built already, but it still needs real information from your environment before it can be completed.

The assistant will probably need to ask you for things like:

- your company name and email domain
- your Power BI workspace ID
- your Power BI dataset ID
- the exact table names to export
- your SharePoint site URL and folder path
- who should receive notifications
- whether this should run locally, in Azure Functions, or with Power Automate

## Important

Do not guess IDs, secrets, or folder paths.

If you do not know one of the required values, ask the assistant to help you find it step by step.

## Main Reference

The main handoff file is:

- `GEMINI_HANDOFF.md`

That file tells the assistant:

- what this project does
- what files matter
- what is already implemented
- what is still placeholder or missing
- what questions it should ask you before making changes
