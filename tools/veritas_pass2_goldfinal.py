#!/usr/bin/env python3
"""Final verified Pass 2 manifest.

The two ADPs were independently confirmed as complete 72-page and 36-page current
editions. Two inaccessible candidates are omitted rather than replaced by stale copies.
"""
from dataclasses import replace

import veritas_pass2_gold  # establishes exact current-source manifest and resolver
import veritas_pass2_builder as b

OMIT = {
    "FM_3-09_Fire_Support_and_Field_Artillery_Operations_2024.pdf",
    "FM_5-0_Planning_and_Orders_Production_2024.pdf",
}

updated = []
for entry in b.ENTRIES:
    if entry.filename in OMIT:
        continue
    if entry.filename == "ADP_3-0_Operations_2025.pdf":
        entry = replace(entry, min_pages=70)
    elif entry.filename == "ADP_7-0_Training_2024.pdf":
        entry = replace(entry, min_pages=35)
    updated.append(entry)

b.ENTRIES = tuple(updated)

if __name__ == "__main__":
    raise SystemExit(b.main())
