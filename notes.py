#!/usr/bin/env python3
"""
notes.py - a minimal, repo-local notes CLI for a markdown+git vault.

Python 3.10+
Optional:
  - ripgrep (rg) for fast search
  - fzf for interactive pick/done
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple, List


# ----------------------------
# Paths / Vault layout
# ----------------------------

# Default to the repo where this script lives so the CLI stays scoped to the checked-out vault.
DEFAULT_VAULT = Path(__file__).resolve().parent
VAULT = Path(os.environ.get("NOTES_VAULT", str(DEFAULT_VAULT))).expanduser()
INBOX = VAULT / "inbox"
DAILY = VAULT / "daily"
TOPICS = VAULT / "topics"
PEOPLE = VAULT / "people"
ASSETS = VAULT / "assets"
INDEX = VAULT / ".index"

ACTIONS_MD = TOPICS / "actions.md"


# ----------------------------
# Note template / parsing
# ----------------------------

FRONTMATTER = """---
id: {id}
created: {date}
tags: [{tags}]
status: {status}
---

# {title}

"""

TASK_OPEN_RE = re.compile(r"^\s*[-*]\s+\[\s\]\s+(.*)\s*$")
TASK_DONE_RE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+(.*)\s*$")
DUE_RE = re.compile(r"@due\((\d{4}-\d{2}-\d{2})\)")
TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9][A-Za-z0-9/_-]*)")
PRIORITY_RE = re.compile(r"(?:^|\s)(P[123])(?:\s|$)")


# ----------------------------
# Helpers
# ----------------------------

def now_id() -> str:
    t = dt.datetime.now()
    return t.strftime("%Y-%m-%d-%H%M")


def today() -> str:
    return dt.date.today().isoformat()


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "note"


def ensure_dirs() -> None:
    for p in (INBOX, DAILY, TOPICS, PEOPLE, ASSETS, INDEX):
        p.mkdir(parents=True, exist_ok=True)


def write_note(path: Path, title: str, tags: list[str], status: str, body: str | None) -> None:
    tag_str = ", ".join(tags)
    content = FRONTMATTER.format(
        id=now_id(),
        date=today(),
        tags=tag_str,
        status=status,
        title=title if title else "Untitled",
    )
    if body:
        content += body.strip() + "\n"
    else:
        # Include a placeholder task line but it will be ignored by the task collector if empty.
        content += "## Context\n\n\n## Notes\n\n\n## Next actions\n- [ ] \n"

    path.write_text(content, encoding="utf-8")


def shutil_which(cmd: str) -> Optional[str]:
    from shutil import which
    return which(cmd)


def open_in_editor(path: Path) -> None:
    """
    Supports multi-arg editors via VISUAL, fallback to EDITOR, then nano.
    Examples:
      export VISUAL="windsurf"
      export VISUAL="windsurf --wait"
      export EDITOR="nvim"
    """
    import shlex
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    subprocess.run(shlex.split(editor) + [str(path)], check=False)


def iter_markdown_files(root: Path) -> Iterable[Path]:
    """
    Iterate markdown notes to scan.
    Important exclusions:
      - .git
      - .index (generated)
      - topics/actions.md (generated; scanning it causes duplicates/self-references)
    """
    for p in root.rglob("*.md"):
        if ".git" in p.parts:
            continue
        if INDEX.name in p.parts:
            continue
        # Don't scan the generated dashboard.
        try:
            if p.resolve() == ACTIONS_MD.resolve():
                continue
        except Exception:
            pass
        yield p


def relpath(p: Path) -> str:
    try:
        return str(p.relative_to(VAULT))
    except Exception:
        return str(p)


# ----------------------------
# Task model + parsing
# ----------------------------

@dataclass(frozen=True)
class Task:
    src_path: Path
    line_no: int
    text: str
    due: Optional[dt.date]
    tags: Tuple[str, ...]
    priority: Optional[str]


def parse_due(text: str) -> Optional[dt.date]:
    m = DUE_RE.search(text)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def parse_tags(text: str) -> Tuple[str, ...]:
    tags = TAG_RE.findall(text)
    uniq: List[str] = []
    seen = set()
    for t in tags:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return tuple(uniq)


def parse_priority(text: str) -> Optional[str]:
    m = PRIORITY_RE.search(text)
    return m.group(1) if m else None


def collect_open_tasks() -> List[Task]:
    tasks: List[Task] = []
    for md in iter_markdown_files(VAULT):
        try:
            lines = md.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines, 1):
            m = TASK_OPEN_RE.match(line)
            if not m:
                continue
            text = m.group(1).strip()

            # Ignore placeholder/template tasks like "- [ ]" with no content.
            if not text:
                continue

            due = parse_due(text)
            tags = parse_tags(text)
            pr = parse_priority(text)
            tasks.append(Task(src_path=md, line_no=i, text=text, due=due, tags=tags, priority=pr))

    return tasks


# ----------------------------
# Actions dashboard generation
# ----------------------------

def generate_actions_md(tasks: List[Task], due_days: int = 7) -> str:
    ensure_dirs()
    today_d = dt.date.today()
    soon_cutoff = today_d + dt.timedelta(days=due_days)

    def sort_key(t: Task):
        due_key = t.due or dt.date(9999, 12, 31)
        pr_key = {"P1": 1, "P2": 2, "P3": 3}.get(t.priority or "P3", 3)
        return (due_key, pr_key, relpath(t.src_path), t.line_no)

    tasks_sorted = sorted(tasks, key=sort_key)

    overdue = [t for t in tasks_sorted if t.due and t.due < today_d]
    due_soon = [t for t in tasks_sorted if t.due and today_d <= t.due <= soon_cutoff]
    no_due = [t for t in tasks_sorted if not t.due]

    def fmt_task(t: Task) -> str:
        # Don't duplicate tags/priority/due; they're already part of t.text if you wrote them.
        src = f"{relpath(t.src_path)}:L{t.line_no}"
        return f"- [ ] {t.text} — ({src})"

    header = [
        "---",
        f"generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"due_window_days: {due_days}",
        "---",
        "",
        "# Actions",
        "",
        "Canonical task list compiled from all open `- [ ]` items across the vault.",
        "",
        "Tips:",
        "- Add due dates like `@due(YYYY-MM-DD)` anywhere in the task text.",
        "- Add tags like `#project/studyscope` to group/filter mentally.",
        "- Put tasks where the context is (daily/inbox/topics/people); this page is the roll-up.",
        "",
    ]

    def section(title: str, items: List[Task]) -> List[str]:
        out = [f"## {title}", ""]
        if not items:
            out += ["(none)", ""]
            return out
        out += [fmt_task(t) for t in items]
        out += [""]
        return out

    lines: List[str] = []
    lines += header
    lines += section("Overdue", overdue)
    lines += section(f"Due soon (next {due_days} days)", due_soon)
    lines += section("No due date", no_due)

    return "\n".join(lines).rstrip() + "\n"


def write_actions(due_days: int = 7) -> Path:
    ensure_dirs()
    tasks = collect_open_tasks()
    content = generate_actions_md(tasks, due_days=due_days)
    ACTIONS_MD.write_text(content, encoding="utf-8")
    return ACTIONS_MD


# ----------------------------
# Commands
# ----------------------------

def cmd_capture(args: argparse.Namespace) -> None:
    ensure_dirs()
    title = args.title or "Quick capture"
    tags = args.tags or []
    filename = f"{today()}-{now_id()}-{slugify(title)[:60]}.md"
    out = INBOX / filename
    write_note(out, title=title, tags=tags, status="inbox", body=args.body)
    print(out)
    if args.edit:
        open_in_editor(out)


def cmd_daily(args: argparse.Namespace) -> None:
    ensure_dirs()
    d = today()
    out = DAILY / f"{d}.md"
    if not out.exists():
        title = f"Daily — {d}"
        write_note(out, title=title, tags=["daily"], status="daily", body=None)
    print(out)
    open_in_editor(out)


def cmd_topic(args: argparse.Namespace) -> None:
    ensure_dirs()
    title = args.title
    tags = args.tags or []
    out = TOPICS / f"{slugify(title)}.md"
    if not out.exists():
        write_note(out, title=title, tags=["topic"] + tags, status="topic", body=args.body)
    print(out)
    if args.edit:
        open_in_editor(out)


def rg_search(pattern: str, paths: Iterable[Path]) -> int:
    rg = shutil_which("rg")
    if rg:
        cmd = [
            rg, "-n", "--hidden",
            "--glob", "!.git/*",
            "--glob", "!/.index/*",
            "--glob", "!topics/actions.md",
            pattern
        ] + [str(p) for p in paths]
        return subprocess.call(cmd)

    pat = re.compile(pattern, re.IGNORECASE)
    hits = 0
    for root in paths:
        for md in root.rglob("*.md"):
            if ".git" in md.parts or INDEX.name in md.parts:
                continue
            try:
                if md.resolve() == ACTIONS_MD.resolve():
                    continue
            except Exception:
                pass

            try:
                lines = md.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    print(f"{md}:{i}:{line}")
                    hits += 1
    return 0 if hits else 1


def cmd_search(args: argparse.Namespace) -> None:
    ensure_dirs()
    sys.exit(rg_search(args.pattern, [VAULT]))


def cmd_pick(args: argparse.Namespace) -> None:
    ensure_dirs()
    fzf = shutil_which("fzf")
    if not fzf:
        print("fzf not found. Install fzf or use `notes search PATTERN`.", file=sys.stderr)
        sys.exit(2)

    files = [str(p) for p in sorted(iter_markdown_files(VAULT))]
    p = subprocess.run([fzf], input="\n".join(files).encode("utf-8"), stdout=subprocess.PIPE, check=False)
    choice = p.stdout.decode("utf-8").strip()
    if choice:
        open_in_editor(Path(choice))


def cmd_actions(args: argparse.Namespace) -> None:
    out = write_actions(due_days=args.due_days)
    print(out)
    if args.open:
        open_in_editor(out)


def replace_line_in_file(path: Path, line_no: int, new_line: str) -> None:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if line_no < 1 or line_no > len(lines):
        raise ValueError("line number out of range")
    lines[line_no - 1] = new_line
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def cmd_done(args: argparse.Namespace) -> None:
    """
    Interactive: pick an open task (via fzf) and mark it done in its source file.
    """
    ensure_dirs()
    fzf = shutil_which("fzf")
    if not fzf:
        print("fzf not found. Install fzf (brew install fzf) or mark tasks manually.", file=sys.stderr)
        sys.exit(2)

    tasks = collect_open_tasks()
    if not tasks:
        print("No open tasks found.")
        return

    # Tab-delimited rows so parsing is stable.
    rows: List[str] = []
    for t in tasks:
        due = t.due.isoformat() if t.due else "NONE"
        pr = t.priority or "P3"
        src = f"{relpath(t.src_path)}:L{t.line_no}"
        rows.append(f"{pr}\t{due}\t{src}\t{t.text}")

    # Show fields nicely; still returns the original line.
    fzf_cmd = [fzf, "--delimiter=\t", "--with-nth=1,2,3,4"]
    proc = subprocess.run(
        fzf_cmd,
        input="\n".join(rows).encode("utf-8"),
        stdout=subprocess.PIPE,
        check=False
    )
    choice = proc.stdout.decode("utf-8").strip()
    if not choice:
        return

    # Parse robustly:
    src_path: Optional[Path] = None
    line_no: Optional[int] = None

    # 1) preferred: tab-delimited
    if "\t" in choice:
        try:
            _pr, _due, src, _text = choice.split("\t", 3)
            src_path_str, line_str = src.split(":L", 1)
            src_path = VAULT / src_path_str
            line_no = int(line_str)
        except Exception:
            src_path = None
            line_no = None

    # 2) fallback: regex find "something.md:L123"
    if src_path is None or line_no is None:
        m = re.search(r"([A-Za-z0-9._/\-]+\.md):L(\d+)", choice)
        if m:
            src_path = VAULT / m.group(1)
            line_no = int(m.group(2))

    if src_path is None or line_no is None:
        print("Could not parse selection.", file=sys.stderr)
        sys.exit(2)

    # Change the checkbox on that line from [ ] to [x]
    lines = src_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if line_no < 1 or line_no > len(lines):
        print("Selected task line no longer exists.", file=sys.stderr)
        sys.exit(2)

    old = lines[line_no - 1]
    if TASK_OPEN_RE.match(old):
        new = re.sub(r"\[\s\]", "[x]", old, count=1)
        replace_line_in_file(src_path, line_no, new)
        print(f"Marked done: {relpath(src_path)}:L{line_no}")
    else:
        print("Selected line is no longer an open task.", file=sys.stderr)

    # Regenerate actions.md
    out = write_actions(due_days=args.due_days)
    if args.open_actions:
        open_in_editor(out)
    if args.open_source:
        open_in_editor(src_path)


# ----------------------------
# Main
# ----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(prog="notes", description="Markdown notes CLI for a git vault.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("capture", help="Quick capture into inbox/")
    p.add_argument("title", nargs="?", default=None)
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--body", default=None, help="Optional body text (otherwise uses a template).")
    p.add_argument("--edit", action="store_true", help="Open in $VISUAL/$EDITOR after creating.")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("daily", help="Open today's daily note in daily/")
    p.set_defaults(func=cmd_daily)

    p = sub.add_parser("topic", help="Create/open a topic note in topics/")
    p.add_argument("title")
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--body", default=None)
    p.add_argument("--edit", action="store_true")
    p.set_defaults(func=cmd_topic)

    p = sub.add_parser("search", help="Search notes (uses rg if available).")
    p.add_argument("pattern")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("pick", help="Pick a note with fzf and open it.")
    p.set_defaults(func=cmd_pick)

    p = sub.add_parser("actions", help="Regenerate topics/actions.md from all open tasks.")
    p.add_argument("--due-days", type=int, default=7, help="Define 'Due soon' window in days (default 7).")
    p.add_argument("--open", action="store_true", help="Open topics/actions.md after generating.")
    p.set_defaults(func=cmd_actions)

    p = sub.add_parser("done", help="Pick an open task with fzf, mark it done, then regenerate actions.")
    p.add_argument("--due-days", type=int, default=7, help="Due soon window used when regenerating actions.")
    p.add_argument("--open-actions", action="store_true", help="Open topics/actions.md after marking done.")
    p.add_argument("--open-source", action="store_true", help="Open the source note where the task lived.")
    p.set_defaults(func=cmd_done)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
