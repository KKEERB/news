# news — Daily Bilingual LLM/Skills/Agents Tip Bot

A GitHub Actions–powered bot that automatically creates a new Issue every day at **09:00 Asia/Shanghai (01:00 UTC)** with bilingual (Chinese + English) tips about:

- 🤖 **Large Language Model (LLM)** usage tips
- 🛠️ **Skill & Tool** usage tips
- 🧩 **Agent** usage tips

Each issue follows a consistent bilingual format and is labeled with `daily-tip` plus a category label (`llm` / `skills` / `agents`).

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Repository Structure](#repository-structure)
3. [Adding New Tips](#adding-new-tips)
4. [Running Locally](#running-locally)
5. [Adjusting the Schedule / Time](#adjusting-the-schedule--time)
6. [Changing the Issue Title Template](#changing-the-issue-title-template)
7. [Troubleshooting](#troubleshooting)

---

## How It Works

1. `.github/workflows/daily-tip.yml` runs on a cron schedule (`0 1 * * *`).
2. It calls `scripts/daily_tip.py`, which:
   - Reads `state/sent.json` to see which tips have already been published.
   - Picks the next un-sent tip, rotating through categories (`llm → skills → agents → llm → …`).
   - Renders a bilingual Markdown issue body.
   - Creates the issue via the GitHub REST API using `GITHUB_TOKEN`.
   - Appends the tip ID to `state/sent.json` and commits it back to `main`.

---

## Repository Structure

```
.github/
  workflows/
    daily-tip.yml       # Scheduled GitHub Actions workflow
scripts/
  daily_tip.py          # Generator + publisher script
tips/
  llm/
    tips.yaml           # LLM usage tips (YAML list)
  skills/
    tips.yaml           # Skill/tool usage tips (YAML list)
  agents/
    tips.yaml           # Agent usage tips (YAML list)
state/
  sent.json             # Lightweight de-dup state (list of sent tip IDs)
README.md
```

---

## Adding New Tips

Each category's tips live in `tips/<category>/tips.yaml` as a YAML list.
Every tip entry follows this schema:

```yaml
- id: <category>-<NNN>          # unique ID, e.g. llm-006
  title_cn: "中文标题"
  title_en: "English title"
  tips:
    - cn: "第一条技巧（中文）"
      en: "First tip (English)"
    - cn: "第二条技巧（中文）"
      en: "Second tip (English)"
    - cn: "第三条技巧（中文）"
      en: "Third tip (English)"
  prompt_cn: |
    中文提示词示例（多行）
  prompt_en: |
    English prompt example (multi-line)
  pitfall_cn: "常见坑描述（中文）"
  pitfall_en: "Pitfall description (English)"
  further_reading:           # optional
    - https://example.com/link
```

**Steps to add a tip:**

1. Open `tips/<category>/tips.yaml` (where `<category>` is `llm`, `skills`, or `agents`).
2. Append a new entry following the schema above.
3. Use the next sequential ID (e.g., if the last LLM tip is `llm-005`, use `llm-006`).
4. Commit and push to `main`.

The bot will automatically pick up the new tip in the next rotation.

---

## Running Locally

### Prerequisites

```bash
pip install pyyaml
```

### Dry run (no issue created)

```bash
cd /path/to/news
DRY_RUN=1 python scripts/daily_tip.py
```

### Create a real issue locally

```bash
export GITHUB_TOKEN=ghp_your_personal_access_token
export GITHUB_REPO=KKEERB/news      # or your fork
python scripts/daily_tip.py
```

The token needs **`repo`** scope (or at minimum `public_repo` for public repos) plus **`issues: write`**.

---

## Adjusting the Schedule / Time

The workflow schedule is defined in `.github/workflows/daily-tip.yml`:

```yaml
on:
  schedule:
    - cron: "0 1 * * *"   # 01:00 UTC = 09:00 Asia/Shanghai
```

GitHub Actions uses **UTC**. To change the publication time:

| Desired local time | UTC cron |
|---|---|
| 08:00 Asia/Shanghai | `0 0 * * *` |
| 09:00 Asia/Shanghai | `0 1 * * *` *(current default)* |
| 10:00 Asia/Shanghai | `0 2 * * *` |
| 09:00 US/Eastern (EST, UTC-5) | `0 14 * * *` |

Use [crontab.guru](https://crontab.guru/) to verify your expression.

---

## Changing the Issue Title Template

The title is rendered in `scripts/daily_tip.py` inside the `render_issue()` function:

```python
title = f"Daily Tip [{today}] — {en_cat} / {cn_cat}"
```

You can change this string to any format you like. Available variables:

| Variable | Example value |
|---|---|
| `today` | `2026-03-13` |
| `en_cat` | `LLM Usage Tips` |
| `cn_cat` | `大语言模型使用技巧` |
| `tip['title_cn']` | `结构化输出：用 JSON 模式约束模型输出` |
| `tip['title_en']` | `Structured Output: constrain the model with JSON mode` |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Workflow fails with `401 Unauthorized` | `GITHUB_TOKEN` missing or expired | Check the workflow's `permissions` block; for classic PATs, re-generate |
| Issue created but no label | Label doesn't exist yet | The script auto-creates labels on first run; check for API errors in the log |
| Same tip published twice | `state/sent.json` not committed | Ensure the "Commit updated state" step succeeded and the bot has `contents: write` |
| `ModuleNotFoundError: yaml` | PyYAML not installed | The workflow installs it automatically; for local runs: `pip install pyyaml` |
| Tips exhausted | All tips in all categories sent | The script resets automatically and starts over from the beginning |