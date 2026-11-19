"""Claude-style skills: folders containing SKILL.md.

A skill is a plain Markdown playbook with YAML frontmatter:

    ---
    name: trader-risk
    description: Checks every order against hard risk limits.
    ---
    # Risk manager
    ...

Skills are loaded from AI-TRADER/skills (override with AI_TRADER_SKILLS) and can
be enabled, edited, created and deleted from the UI. The agent can read an
enabled skill with the built-in `read_skill` tool.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import SKILLS_DIR
from .db import get_db, new_id, now

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            block = parts[1]
            body = parts[2].lstrip("\n")
            for line in block.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                value = value.strip().strip('"').strip("'")
                meta[key.strip().lower()] = value
    return meta, body


def skill_dirs() -> list[Path]:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file()])


def read_skill(skill_id: str) -> str:
    path = SKILLS_DIR / skill_id / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"Skill '{skill_id}' not found")
    return path.read_text(encoding="utf-8")


def sync_skills() -> int:
    """Discover skills on disk and register new ones. Existing rows keep state."""
    db = get_db()
    seen = 0
    for folder in skill_dirs():
        text = (folder / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        meta, _ = _parse_frontmatter(text)
        name = meta.get("name") or folder.name
        desc = meta.get("description", "")
        existing = db.one("SELECT id FROM skills WHERE id=?", (folder.name,))
        if existing:
            db.execute("UPDATE skills SET name=?, description=?, path=? WHERE id=?",
                       (name, desc, str(folder), folder.name))
        else:
            db.execute(
                "INSERT INTO skills(id,name,description,path,enabled,source,created_at) VALUES(?,?,?,?,?,?,?)",
                (folder.name, name, desc, str(folder), 1, "bundled" if meta.get("source") else "local", now()),
            )
        seen += 1
    return seen


def create_skill(skill_id: str, name: str, description: str, content: str, enabled: bool = True) -> dict:
    if not SAFE_ID.match(skill_id):
        raise ValueError("Skill id must be lowercase letters, numbers, - or _ (2-64 chars)")
    folder = SKILLS_DIR / skill_id
    if folder.exists():
        raise FileExistsError(f"Skill '{skill_id}' already exists")
    folder.mkdir(parents=True)
    body = content if content.strip() else f"# {name}\n\n{description}\n"
    if not body.lstrip().startswith("---"):
        body = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    sync_skills()
    return get_db().one("SELECT * FROM skills WHERE id=?", (skill_id,)) or {}


def update_skill(skill_id: str, **fields) -> dict:
    db = get_db()
    row = db.one("SELECT * FROM skills WHERE id=?", (skill_id,))
    if not row:
        raise FileNotFoundError(skill_id)
    content = fields.get("content")
    if content is not None:
        path = SKILLS_DIR / skill_id / "SKILL.md"
        path.write_text(content, encoding="utf-8")
        meta, _ = _parse_frontmatter(content)
        if meta.get("name"):
            db.execute("UPDATE skills SET name=? WHERE id=?", (meta["name"], skill_id))
        if meta.get("description"):
            db.execute("UPDATE skills SET description=? WHERE id=?", (meta["description"], skill_id))
    if "enabled" in fields:
        db.execute("UPDATE skills SET enabled=? WHERE id=?", (1 if fields["enabled"] else 0, skill_id))
    return db.one("SELECT * FROM skills WHERE id=?", (skill_id,)) or {}


def delete_skill(skill_id: str, delete_files: bool = True) -> None:
    if not SAFE_ID.match(skill_id):
        raise ValueError("Invalid skill id")
    folder = SKILLS_DIR / skill_id
    if delete_files and folder.exists() and folder.parent == SKILLS_DIR:
        shutil.rmtree(folder)
    get_db().execute("DELETE FROM skills WHERE id=?", (skill_id,))


def enabled_skills() -> list[dict]:
    return get_db().query("SELECT * FROM skills WHERE enabled=1 ORDER BY name")


def skill_catalog() -> list[dict]:
    rows = get_db().query("SELECT * FROM skills ORDER BY name")
    for row in rows:
        try:
            text = read_skill(row["id"])
            row["size"] = len(text)
            row["preview"] = text[:600]
        except FileNotFoundError:
            row["size"] = 0
            row["preview"] = ""
    return rows


def ensure_default_skill_meta() -> None:
    """Make sure the folder exists before the first scan."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
