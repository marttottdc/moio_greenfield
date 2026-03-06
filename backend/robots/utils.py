from __future__ import annotations


def hhmm_to_minutes(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("Time must be a string in HH:MM format")
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Time must be in HH:MM format")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Time must be in HH:MM format")
    return hour * 60 + minute


def is_within_operation_window(*, start_hhmm: str, end_hhmm: str, current_hhmm: str) -> bool:
    start = hhmm_to_minutes(start_hhmm)
    end = hhmm_to_minutes(end_hhmm)
    current = hhmm_to_minutes(current_hhmm)
    if start <= end:
        return start <= current <= end
    # Cross-midnight window, e.g. 22:00 -> 06:00.
    return current >= start or current <= end

