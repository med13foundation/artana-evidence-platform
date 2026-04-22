"""Cron parsing and matching helpers for the Postgres scheduler backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

CRON_MIN_FIELDS = 5
CRON_LOOKAHEAD_DAYS = 366
CRON_MINUTE_VALUES = 60
CRON_HOUR_VALUES = 24
CRON_MONTH_VALUES = 12
CRON_SUNDAY_ALIAS = 7


@dataclass(frozen=True)
class _CronSpec:
    minutes: set[int]
    hours: set[int]
    days_of_month: set[int]
    months: set[int]
    days_of_week: set[int]
    day_of_month_is_any: bool
    day_of_week_is_any: bool


def next_cron_occurrence(*, expression: str, reference: datetime) -> datetime:
    spec = _parse_cron_expression(expression)
    candidate = reference.replace(second=0, microsecond=0) + timedelta(minutes=1)
    search_deadline = candidate + timedelta(days=CRON_LOOKAHEAD_DAYS)

    while candidate <= search_deadline:
        if _cron_matches(spec=spec, candidate=candidate):
            return candidate
        candidate += timedelta(minutes=1)

    msg = (
        "No matching run time found for cron expression within "
        f"{CRON_LOOKAHEAD_DAYS} days"
    )
    raise ValueError(msg)


def _cron_matches(*, spec: _CronSpec, candidate: datetime) -> bool:
    if candidate.minute not in spec.minutes:
        return False
    if candidate.hour not in spec.hours:
        return False
    if candidate.month not in spec.months:
        return False

    day_of_month_match = candidate.day in spec.days_of_month
    day_of_week_match = _cron_day_of_week(candidate) in spec.days_of_week

    if spec.day_of_month_is_any and spec.day_of_week_is_any:
        day_match = True
    elif spec.day_of_month_is_any:
        day_match = day_of_week_match
    elif spec.day_of_week_is_any:
        day_match = day_of_month_match
    else:
        day_match = day_of_month_match or day_of_week_match

    return day_match


def _cron_day_of_week(value: datetime) -> int:
    # Python: Monday=0..Sunday=6; Cron: Sunday=0, Monday=1..Saturday=6
    return (value.weekday() + 1) % 7


def _parse_cron_expression(expression: str) -> _CronSpec:
    fields = expression.split()
    if len(fields) != CRON_MIN_FIELDS:
        msg = (
            "Cron expression must contain exactly five fields: "
            "minute hour day-of-month month day-of-week"
        )
        raise ValueError(msg)

    minutes, minute_any = _parse_cron_field(fields[0], 0, 59)
    hours, hour_any = _parse_cron_field(fields[1], 0, 23)
    days_of_month, dom_any = _parse_cron_field(fields[2], 1, 31)
    months, month_any = _parse_cron_field(fields[3], 1, 12)
    days_of_week_raw, dow_any = _parse_cron_field(
        fields[4],
        0,
        7,
        allow_seven_as_sunday=True,
    )

    if minute_any and len(minutes) != CRON_MINUTE_VALUES:
        msg = "Cron minute wildcard parsing error"
        raise ValueError(msg)
    if hour_any and len(hours) != CRON_HOUR_VALUES:
        msg = "Cron hour wildcard parsing error"
        raise ValueError(msg)
    if month_any and len(months) != CRON_MONTH_VALUES:
        msg = "Cron month wildcard parsing error"
        raise ValueError(msg)

    days_of_week = {
        0 if value == CRON_SUNDAY_ALIAS else value for value in days_of_week_raw
    }
    return _CronSpec(
        minutes=minutes,
        hours=hours,
        days_of_month=days_of_month,
        months=months,
        days_of_week=days_of_week,
        day_of_month_is_any=dom_any,
        day_of_week_is_any=dow_any,
    )


def _parse_cron_field(
    field_value: str,
    minimum: int,
    maximum: int,
    *,
    allow_seven_as_sunday: bool = False,
) -> tuple[set[int], bool]:
    normalized = field_value.strip()
    if not normalized:
        msg = "Cron field cannot be empty"
        raise ValueError(msg)
    if normalized == "*":
        return set(range(minimum, maximum + 1)), True

    result: set[int] = set()
    for segment in normalized.split(","):
        expanded = _expand_cron_segment(
            segment=segment.strip(),
            minimum=minimum,
            maximum=maximum,
            allow_seven_as_sunday=allow_seven_as_sunday,
        )
        result.update(expanded)
    return result, False


def _expand_cron_segment(
    *,
    segment: str,
    minimum: int,
    maximum: int,
    allow_seven_as_sunday: bool,
) -> set[int]:
    if not segment:
        msg = "Cron segment cannot be empty"
        raise ValueError(msg)

    if "/" in segment:
        base_segment, step_segment = segment.split("/", 1)
        step = _parse_step_value(step_segment)
        if base_segment == "*":
            start = minimum
            end = maximum
        else:
            start, end = _parse_cron_range(
                base_segment,
                minimum=minimum,
                maximum=maximum,
                allow_seven_as_sunday=allow_seven_as_sunday,
            )
        return set(range(start, end + 1, step))

    if segment == "*":
        return set(range(minimum, maximum + 1))

    if "-" in segment:
        start, end = _parse_cron_range(
            segment,
            minimum=minimum,
            maximum=maximum,
            allow_seven_as_sunday=allow_seven_as_sunday,
        )
        return set(range(start, end + 1))

    value = _parse_cron_value(
        segment,
        minimum=minimum,
        maximum=maximum,
        allow_seven_as_sunday=allow_seven_as_sunday,
    )
    return {value}


def _parse_cron_range(
    segment: str,
    *,
    minimum: int,
    maximum: int,
    allow_seven_as_sunday: bool,
) -> tuple[int, int]:
    start_text, end_text = segment.split("-", 1)
    start = _parse_cron_value(
        start_text,
        minimum=minimum,
        maximum=maximum,
        allow_seven_as_sunday=allow_seven_as_sunday,
    )
    end = _parse_cron_value(
        end_text,
        minimum=minimum,
        maximum=maximum,
        allow_seven_as_sunday=allow_seven_as_sunday,
    )
    if start > end:
        msg = f"Invalid cron range '{segment}': start must be <= end"
        raise ValueError(msg)
    return start, end


def _parse_cron_value(
    segment: str,
    *,
    minimum: int,
    maximum: int,
    allow_seven_as_sunday: bool,
) -> int:
    value = _parse_int(segment, "Cron value")
    if allow_seven_as_sunday and value == CRON_SUNDAY_ALIAS:
        return CRON_SUNDAY_ALIAS
    if value < minimum or value > maximum:
        msg = f"Cron value {value} out of range ({minimum}-{maximum})"
        raise ValueError(msg)
    return value


def _parse_int(raw_value: str, field_name: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        msg = f"{field_name} must be an integer: '{raw_value}'"
        raise ValueError(msg) from exc
    return value


def _parse_step_value(raw_value: str) -> int:
    value = _parse_int(raw_value, "Cron step")
    if value <= 0:
        msg = f"Cron step must be greater than zero: '{raw_value}'"
        raise ValueError(msg)
    return value
