from __future__ import annotations

from typing import Any


def build_diff_message(old: dict[str, Any], new: dict[str, Any]) -> str | None:
    if old == new:
        return None

    lines: list[str] = []
    new_overall = new.get("overall", "Unknown")
    old_overall = old.get("overall", "Unknown")

    if new_overall == "Healthy" and old_overall != "Healthy":
        lines.append("✅ LinguiCards.API is back to Healthy!")
    elif new_overall != old_overall:
        lines.append(
            "⚠️ LinguiCards.API health status changed!\n"
            f"Overall: {old_overall} → {new_overall}"
        )
    else:
        lines.append("⚠️ LinguiCards.API health check update:")

    check_names = sorted(set(list(old.keys()) + list(new.keys())) - {"overall"})
    if check_names:
        lines.append("\nChecks:")
    for name in check_names:
        old_check = old.get(name, {})
        new_check = new.get(name, {})
        old_s = old_check.get("status", "N/A") if isinstance(old_check, dict) else "N/A"
        new_s = new_check.get("status", "N/A") if isinstance(new_check, dict) else "N/A"
        new_err = new_check.get("error") if isinstance(new_check, dict) else None

        if old_s != new_s:
            lines.append(f"  • {name}: {old_s} → {new_s}")
        else:
            lines.append(f"  • {name}: {new_s}")

        if new_err:
            lines.append(f"    Error: {new_err}")

    return "\n".join(lines)


def format_current_status(status: dict[str, Any]) -> str:
    lines = [f"Overall: {status.get('overall', 'Unknown')}"]
    check_names = sorted(set(status.keys()) - {"overall"})
    if check_names:
        lines.append("\nChecks:")
    for name in check_names:
        info = status.get(name, {})
        if isinstance(info, dict):
            s = info.get("status", "Unknown")
            err = info.get("error")
            lines.append(f"  • {name}: {s}")
            if err:
                lines.append(f"    Error: {err}")
        else:
            lines.append(f"  • {name}: {info}")
    return "\n".join(lines)

