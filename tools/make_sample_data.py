#!/usr/bin/env python3
"""Generate ``samples/sample_performance_data.json``: a small, synthetic Power BI Performance Analyzer export.

It is not a real recording. The queries are ``EVALUATE ROW(...)`` statements that are valid against any semantic model, so the file
can be used for smoke tests and for the unit tests. Record your own navigation with Performance Analyzer for real load tests.

The shape of the data is deliberate: 5 user actions with different labels, 1 to 3 queries per action, and the queries of one
action listed out of chronological order (as real exports do), so that the think-time parser is exercised.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

# (label, action offset in seconds, [(visual title, query start offset, query end offset), ...])
ACTIONS = [
    ("UserAction_OpenReport", 0.0, [("Sales by Category", 0.10, 0.50), ("Orders by Month", 0.12, 0.80), ("Top Customers", 0.15, 1.20)]),
    ("UserAction_ChangeSlicer", 6.0, [("Sales by Category", 6.10, 6.70), ("Orders by Month", 6.20, 6.90)]),
    ("UserAction_CrossHighlight", 13.0, [("Sales by Category", 13.10, 13.50), ("Orders by Month", 13.10, 13.90), ("Top Customers", 13.20, 14.50)]),
    ("UserAction_Drill", 16.0, [("Top Customers", 16.10, 16.40)]),
    ("UserAction_CrossHighlight", 25.0, [("Sales by Category", 25.10, 25.60), ("Orders by Month", 25.15, 26.00)]),
]
# Think time (seconds) expected before each action, computed as: action start - end of the last query of the previous action.
EXPECTED_THINK_TIMES = [0.0, 4.8, 6.1, 1.5, 8.6]


def iso(offset: float) -> str:
    return (BASE + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build() -> dict:
    events, n = [], 0
    for a_index, (label, a_start, queries) in enumerate(ACTIONS, start=1):
        events.append({"name": "User Action", "component": "Report Canvas", "start": iso(a_start),
                       "id": f"action-{a_index:02d}", "metrics": {"sourceLabel": label}})
        ordered = list(queries)
        if a_index == 3:
            ordered.reverse()  # not chronological in the file
        for title, q_start, q_end in ordered:
            n += 1
            events.append({"name": "Visual Container Lifecycle", "start": iso(q_start), "id": f"visual-{n:02d}",
                           "metrics": {"visualTitle": title, "visualId": "visual-" + title.lower().replace(" ", "-"),
                                       "visualType": "tableEx", "status": "Success", "initialLoad": False}})
            events.append({"name": "Execute DAX Query", "start": iso(q_start), "end": iso(q_end), "id": f"query-{n:02d}",
                           "parentId": f"visual-{n:02d}", "metrics": {"QueryText": f'EVALUATE ROW("Query", {n})', "RowCount": 1}})
            events.append({"name": "Render", "start": iso(q_end), "end": iso(q_end + 0.05), "id": f"render-{n:02d}", "metrics": {}})
    return {"version": "1.1.0", "events": events}


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "samples" / "sample_performance_data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"{out} written ({len(build()['events'])} events)")
