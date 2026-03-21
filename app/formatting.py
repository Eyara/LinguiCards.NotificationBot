from __future__ import annotations

from typing import Any


def _ru_status(value: str) -> str:
    return {
        "Healthy": "Здоров",
        "Unhealthy": "Не в норме",
        "Unknown": "Неизвестно",
        "N/A": "н/д",
    }.get(value, value)


def build_diff_message(old: dict[str, Any], new: dict[str, Any]) -> str | None:
    if old == new:
        return None

    lines: list[str] = []
    new_overall = new.get("overall", "Unknown")
    old_overall = old.get("overall", "Unknown")

    if new_overall == "Healthy" and old_overall != "Healthy":
        lines.append("✅ LinguiCards.API снова в норме!")
    elif new_overall != old_overall:
        lines.append(
            "⚠️ Изменился статус LinguiCards.API!\n"
            f"Общий статус: {_ru_status(old_overall)} → {_ru_status(new_overall)}"
        )
    else:
        lines.append("⚠️ Обновление проверки LinguiCards.API:")

    check_names = sorted(set(list(old.keys()) + list(new.keys())) - {"overall"})
    if check_names:
        lines.append("\nПроверки:")
    for name in check_names:
        old_check = old.get(name, {})
        new_check = new.get(name, {})
        old_s = old_check.get("status", "N/A") if isinstance(old_check, dict) else "N/A"
        new_s = new_check.get("status", "N/A") if isinstance(new_check, dict) else "N/A"
        new_err = new_check.get("error") if isinstance(new_check, dict) else None

        if old_s != new_s:
            lines.append(f"  • {name}: {_ru_status(old_s)} → {_ru_status(new_s)}")
        else:
            lines.append(f"  • {name}: {_ru_status(new_s)}")

        if new_err:
            lines.append(f"    Ошибка: {new_err}")

    return "\n".join(lines)


def format_current_status(status: dict[str, Any]) -> str:
    ov = status.get("overall", "Unknown")
    lines = [f"Общий статус: {_ru_status(ov)}"]
    check_names = sorted(set(status.keys()) - {"overall"})
    if check_names:
        lines.append("\nПроверки:")
    for name in check_names:
        info = status.get(name, {})
        if isinstance(info, dict):
            s = info.get("status", "Unknown")
            err = info.get("error")
            lines.append(f"  • {name}: {_ru_status(s)}")
            if err:
                lines.append(f"    Ошибка: {err}")
        else:
            lines.append(f"  • {name}: {info}")
    return "\n".join(lines)

