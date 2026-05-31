"""Verify date anchor injection and add_to_calendar validation.

Run:
    python tests/manual_date_anchors.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api.services.chat_agent import _build_system_prompt  # noqa: E402


def main() -> int:
    system_prompt = _build_system_prompt()

    print("=" * 70)
    print("System Prompt Date Anchors")
    print("=" * 70)

    # Extract the date anchor section
    lines = system_prompt.split("\n")
    in_anchors = False
    for line in lines:
        if "Current date anchors" in line:
            in_anchors = True
        if in_anchors:
            print(line)
            if line.startswith("When the user"):
                break

    print("\n" + "=" * 70)
    print("Validation Checks")
    print("=" * 70)

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    monday_this_week = today - timedelta(days=today.weekday())
    next_monday = monday_this_week + timedelta(days=7)

    checks = [
        ("Today in prompt", today.strftime("%Y-%m-%d") in system_prompt),
        ("Tomorrow in prompt", tomorrow.strftime("%Y-%m-%d") in system_prompt),
        ("Next Monday in prompt", next_monday.strftime("%Y-%m-%d") in system_prompt),
        ("Warning about training data", "Never invent a date from training data" in system_prompt),
        ("Requirement: date >= today", "MUST be ≥" in system_prompt),
    ]

    all_pass = True
    for check_name, passed in checks:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {check_name}")
        if not passed:
            all_pass = False

    print("=" * 70)

    if all_pass:
        print("[OK] All date anchor checks passed")
        return 0
    else:
        print("[FAIL] Some checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
