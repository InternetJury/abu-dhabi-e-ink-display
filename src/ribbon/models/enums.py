from enum import StrEnum


class ModeName(StrEnum):
    WEEKDAY_COMMUTE_NOW = "weekday_commute_now"
    AMBIENT_INFO = "ambient_info"
    WEEKEND_MULTI_STOP = "weekend_multi_stop"

    @classmethod
    def _missing_(cls, value: object):
        aliases = {
            "commute_now": cls.WEEKDAY_COMMUTE_NOW,
            "city_pulse": cls.AMBIENT_INFO,
            "service_overview": cls.AMBIENT_INFO,
        }
        return aliases.get(value)


class RefreshHint(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"


class FrequencyBand(StrEnum):
    FREQUENT = "frequent"
    MODERATE = "moderate"
    SPARSE = "sparse"
    UNKNOWN = "unknown"


class LeaveByStatus(StrEnum):
    LEAVE_NOW = "leave_now"
    LEAVE_SOON = "leave_soon"
    BUFFERED = "buffered"
    MISSED = "missed"
    UNAVAILABLE = "unavailable"


class MarketDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
