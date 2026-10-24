from enum import Enum


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
