from pagercutie.core.enums import Channel, Severity
from pagercutie.preferences.resolution import fallback_channels
from pagercutie.preferences.schemas import ChannelPreferences


def prefs(*rules: dict[str, object]) -> ChannelPreferences:
    return ChannelPreferences.model_validate({"rules": list(rules)})


def test_fallback_follows_the_matching_rules_in_order_then_email() -> None:
    preferences = prefs(
        {"min_severity": "critical", "channels": ["phone", "sms"], "window": {"start": "08:00", "end": "20:00"}},
        {"min_severity": "error", "channels": ["ui", "sms"]},
        {"min_severity": "info", "channels": ["email"]},
    )

    assert fallback_channels(preferences, Severity.CRITICAL) == [Channel.PHONE, Channel.SMS, Channel.EMAIL]


def test_rules_for_higher_severities_are_left_out() -> None:
    preferences = prefs({"min_severity": "critical", "channels": ["phone"]})

    assert fallback_channels(preferences, Severity.WARN) == [Channel.EMAIL]


def test_without_preferences_email_is_the_only_fallback() -> None:
    assert fallback_channels(prefs(), Severity.CRITICAL) == [Channel.EMAIL]
