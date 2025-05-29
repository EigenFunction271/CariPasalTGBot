# Loophole Hackers Telegram Bot - Project Tracker

## Summary
A custom Telegram bot to let builders at Loophole Hackers self-report project progress, reducing ops overhead and enabling automated tracking via Airtable. Deployed on Render, it serves as a lightweight interface for project creation, updates, and basic browsing via Telegram chat.

---

## Objectives
- Allow users to create and update project records directly via Telegram
- Automatically sync submissions to Airtable
- Send weekly reminders to update
- Reduce manual tracking and form fatigue
- Support future integrations with Notion or public dashboards

---

## Core Features

### 1. `/newproject`
- Collect:
  - Project name
  - One-liner tagline
  - Problem statement
  - Tech stack (free text)
  - GitHub or demo link
  - Current stage (Idea, MVP, Launched)
  - Help needed (free text)
- Save to Airtable

### 2. `/updateproject`
- List user’s existing projects (via Telegram ID)
- Collect:
  - Progress made this week
  - Blockers
- Save to Airtable as a new row in `Updates` table

### 3. `/myprojects`
- Fetch user projects from Airtable
- Return list of summaries with buttons for update

---

## Database: Airtable

### Table: `Projects`
| Field             | Type           |
|------------------|----------------|
| Project Name      | Text           |
| Owner Telegram ID | Text           |
| One-liner         | Text           |
| Problem Statement | Long text      |
| Stack             | Text           |
| GitHub/Demo       | URL            |
| Status            | Single select  |
| Help Needed       | Long text      |
| Last Updated      | Date           |

### Table: `Updates`
| Field             | Type           |
|------------------|----------------|
| Project (Linked)  | Link to Project|
| Update Text       | Long text      |
| Blockers          | Long text      |
| Updated By        | Telegram ID    |
| Timestamp         | Date           |

---

## Deployment
- Host on Render (Flask backend with webhook)
- Use Telegram webhook instead of polling
- Telegram bot created via BotFather

---

## Future Features
- Weekly digest broadcast
- Notion sync or embed
- LLM summary of updates
- Contributor matchmaking
- Role-based help requests

---

## Success Criteria
- Builders actively using the bot for updates
- Reduced need for ops to manually collect project data
- Airtable populated with current project metadata
