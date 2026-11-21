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


class Role(StrEnum):
    """A backend process role (SPEC §3.2). One process runs one or more roles."""

    INGEST = "ingest"
    EVALUATOR = "evaluator"
    DEDUP = "dedup"
    DISPATCHER = "dispatcher"
    EXECUTOR = "executor"
    API = "api"


class RoleGroup(StrEnum):
    """A name for a set of roles run by one process (SPEC §3.2)."""

    WORKER = "worker"
    ALL = "all"
