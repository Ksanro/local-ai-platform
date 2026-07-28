# Archive

This directory is for historical designs and dormant architecture notes.

Archived docs may describe useful ideas, but they are not evidence that a
feature runs in the live gateway. A feature is live only when it is reachable
from `apps/gateway/main.py` or a gateway endpoint and is reflected in
`docs/STATUS.md`.

Before moving a document out of archive, update:

- `docs/STATUS.md`
- `docs/roadmap.md`
- `docs/index.md`
- focused tests for the live path
- session logging or measurement docs when behavior affects live traffic
