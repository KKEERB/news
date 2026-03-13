#!/usr/bin/env python3
"""
daily_tip.py — Daily bilingual LLM/skills/agents tip publisher.

Selects the next tip from the tips/ library (rotating across categories),
renders a bilingual (Chinese + English) GitHub Issue body, and creates the
issue via the GitHub REST API.

Usage:
    python scripts/daily_tip.py

Required environment variables:
    GITHUB_TOKEN   — token with issues:write permission
    GITHUB_REPO    — target repo in "owner/repo" format (default: KKEERB/news)

Optional environment variables:
    TIPS_DIR       — path to the tips directory (default: tips/)
    STATE_FILE     — path to the sent-state JSON file (default: state/sent.json)
    DRY_RUN        — set to "1" to print the issue body without creating it
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
TIPS_DIR = Path(os.environ.get("TIPS_DIR", REPO_ROOT / "tips"))
STATE_FILE = Path(os.environ.get("STATE_FILE", REPO_ROOT / "state" / "sent.json"))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "KKEERB/news")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

CATEGORIES = ["llm", "skills", "agents"]

# Human-readable category labels used in issue content
CATEGORY_DISPLAY = {
    "llm": ("大语言模型使用技巧", "LLM Usage Tips"),
    "skills": ("技能与工具使用技巧", "Skill & Tool Usage Tips"),
    "agents": ("Agent 使用技巧", "Agent Usage Tips"),
}

# GitHub label names per category
CATEGORY_LABELS = {
    "llm": "llm",
    "skills": "skills",
    "agents": "agents",
}

SHANGHAI_TZ = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load the sent-state JSON file, returning a default if absent."""
    if STATE_FILE.exists():
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"sent": []}


def save_state(state: dict) -> None:
    """Persist the sent-state JSON file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"State saved to {STATE_FILE}")


# ---------------------------------------------------------------------------
# Tips library helpers
# ---------------------------------------------------------------------------

def load_tips(category: str) -> list[dict]:
    """Load all tips for a category from tips/<category>/tips.yaml."""
    tips_file = TIPS_DIR / category / "tips.yaml"
    if not tips_file.exists():
        print(f"ERROR: Tips file not found: {tips_file}", file=sys.stderr)
        sys.exit(1)
    with tips_file.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def pick_tip(state: dict) -> tuple[str, dict]:
    """
    Select the next tip to publish.

    Strategy:
    1. Build an ordered list of (category, tip_id) pairs cycling through
       CATEGORIES in order, each category contributing its tips in sequence.
    2. Skip any pair already in state["sent"].
    3. Return the first unsent pair.
    4. If everything has been sent, clear the history and start over.
    """
    sent_set = set(state.get("sent", []))

    # Gather all (category, tip) pairs in round-robin category order
    all_tips: list[tuple[str, dict]] = []
    cat_tips = {cat: load_tips(cat) for cat in CATEGORIES}
    max_len = max(len(tips) for tips in cat_tips.values())

    for i in range(max_len):
        for cat in CATEGORIES:
            tips = cat_tips[cat]
            if i < len(tips):
                all_tips.append((cat, tips[i]))

    # Find first unsent tip
    for cat, tip in all_tips:
        key = tip["id"]
        if key not in sent_set:
            return cat, tip

    # All tips exhausted — reset and start over
    print("All tips have been sent. Resetting state and starting over.")
    state["sent"] = []
    return all_tips[0]


# ---------------------------------------------------------------------------
# Issue rendering
# ---------------------------------------------------------------------------

def render_issue(category: str, tip: dict, today: str) -> tuple[str, str]:
    """Return (title, body) for the GitHub Issue."""
    cn_cat, en_cat = CATEGORY_DISPLAY[category]

    title = f"Daily Tip [{today}] — {en_cat} / {cn_cat}"

    tips_block = ""
    for idx, t in enumerate(tip.get("tips", []), start=1):
        tips_block += f"**{idx}.** {t['cn']}\n\n> {t['en']}\n\n"

    prompt_cn = tip.get("prompt_cn", "").strip()
    prompt_en = tip.get("prompt_en", "").strip()

    further = tip.get("further_reading", [])
    further_block = ""
    if further:
        further_block = "\n## 📚 延伸阅读 / Further Reading\n\n"
        for link in further:
            further_block += f"- {link}\n"

    body = f"""\
## 今日主题 / Today's Theme

**{tip['title_cn']}**

> {tip['title_en']}

---

## 💡 3 条技巧（中英对照）/ 3 Tips (CN/EN)

{tips_block.rstrip()}

---

## 📋 可复制提示词 / Copy-Paste Prompt

<details>
<summary>中文版 (Chinese)</summary>

```
{prompt_cn}
```

</details>

<details>
<summary>English version</summary>

```
{prompt_en}
```

</details>

---

## ⚠️ 常见坑 / Pitfall

**中文：** {tip.get('pitfall_cn', '')}

**English:** {tip.get('pitfall_en', '')}
{further_block}
---

*Labels: `daily-tip` · `{CATEGORY_LABELS[category]}` · Generated {today} (Asia/Shanghai)*
"""
    return title, body


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def ensure_label(label: str, color: str, description: str) -> None:
    """Create a GitHub label if it doesn't already exist."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/labels/{label}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        urllib.request.urlopen(req)
        return  # Label already exists
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    # Create the label
    payload = json.dumps(
        {"name": label, "color": color, "description": description}
    ).encode()
    create_req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/labels",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        urllib.request.urlopen(create_req)
        print(f"Created label: {label}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Warning: could not create label '{label}': {e.code} {body}", file=sys.stderr)


def create_issue(title: str, body: str, labels: list[str]) -> str:
    """Create a GitHub Issue and return its HTML URL."""
    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.load(resp)
            return result["html_url"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"ERROR creating issue: HTTP {e.code}\n{error_body}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Label definitions
# ---------------------------------------------------------------------------

LABEL_DEFS = {
    "daily-tip": ("0075ca", "Automatically generated daily tip"),
    "llm": ("d93f0b", "Large language model usage tips"),
    "skills": ("0e8a16", "Skill and tool usage tips"),
    "agents": ("e4e669", "Agent usage tips"),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not GITHUB_TOKEN and not DRY_RUN:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
    print(f"Running daily tip publisher for {today} ...")

    # Load state and pick a tip
    state = load_state()
    category, tip = pick_tip(state)
    print(f"Selected tip: {tip['id']} (category: {category})")

    # Render
    title, body = render_issue(category, tip, today)

    if DRY_RUN:
        print("\n--- DRY RUN: Issue would be created with the following content ---\n")
        print(f"Title: {title}\n")
        print(body)
        print("--- END DRY RUN ---")
        return

    # Ensure required labels exist
    for label_name, (color, desc) in LABEL_DEFS.items():
        ensure_label(label_name, color, desc)

    # Create issue
    labels = ["daily-tip", CATEGORY_LABELS[category]]
    issue_url = create_issue(title, body, labels)
    print(f"Issue created: {issue_url}")

    # Update state and persist
    state["sent"].append(tip["id"])
    save_state(state)


if __name__ == "__main__":
    main()
