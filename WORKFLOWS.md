# Workflows

## Capture (fast)
Use when you don't want to decide where a thought belongs yet.

Command:
  notes capture "Title" --tags idea project/foo --edit

Result:
  A new note in inbox/ with a template.

## Daily log (default)
Use for: meetings, tasks for today, what you learned, quick state.

Command:
  notes daily

Pattern inside the daily note:
  - Top: Today’s intent
  - Middle: stream of notes/meetings
  - Bottom: Next actions + carry-overs

## Promote (inbox -> topics/people)
During review, promote anything that is durable.

Manual approach:
  - Create a topic page: notes topic "StudyScope"
  - Copy key info from inbox note into the topic page
  - Add a link back to the source inbox note

Codex-assisted approach:
  - Ask Codex to convert a set of inbox notes into structured topic pages
  - Ask it to extract actions into topics/actions.md

## Revisit (search, pick, hubs)
Fast retrieval:
  notes search "keyword"
  notes pick

Deep retrieval:
  Open a topic hub in topics/ (e.g., topics/studyscope.md) and follow links.

