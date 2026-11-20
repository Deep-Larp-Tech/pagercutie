"""Enums shared by several modules and by the pipeline."""

from enum import StrEnum


class Severity(StrEnum):
    """Ordered from least to most severe; compare with `SEVERITY_ORDER`, not alphabetically."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


SEVERITY_ORDER = {severity: rank for rank, severity in enumerate(Severity)}


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    UI = "ui"


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"
