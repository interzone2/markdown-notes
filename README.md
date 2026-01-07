# Notes Vault

This vault is a CLI-first, git-friendly notes system.

## Folder meanings
- inbox/  : quick capture, unrefined notes (empty this periodically)
- daily/  : one note per day, your running log
- topics/ : evergreen notes / wiki pages / project hubs
- people/ : notes by person (context, meetings, follow-ups)
- assets/ : attachments (pdf/images/audio/etc) referenced from notes
- .index/ : generated indexes/caches (disposable; typically not committed)

## Commands
- notes daily
  Opens today's daily note (daily/YYYY-MM-DD.md)

- notes capture "Title" --tags tag1 tag2 [--edit]
  Creates a new inbox note with YAML frontmatter + template

- notes topic "Topic Name" [--tags tag1 tag2] [--edit]
  Creates/opens a topic note at topics/<slug>.md

- notes search "pattern"
  Searches the vault (uses ripgrep if installed)

- notes pick
  Uses fzf to pick a note and opens it in your editor

## Working rhythm
1) Capture: use inbox/ for anything that arrives mid-flow
2) Log: use daily/ for what happened today + next actions
3) Promote: move durable knowledge into topics/ and people/
4) Revisit: use search/pick + topic hubs to re-enter context

## Recommended conventions
- Prefer writing in daily/ during the day.
- Promote the best ideas into topics/ as clean, reusable pages.
- Keep people context in people/<name>.md.
- Put attachments in assets/ and link to them relatively.

  