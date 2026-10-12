from enum import StrEnum


class Channel(StrEnum):
    ACTIVITY = "activity"
    DIALOGUE = "dialogue"
    CG = "cg"
    EXTERNAL_MEDIA = "external_media"
    INTERFACE = "interface"


CHANNEL_LABELS = {
    Channel.ACTIVITY: "角色行進與交互",
    Channel.DIALOGUE: "角色對話與彼此交互",
    Channel.CG: "一般 CG",
    Channel.EXTERNAL_MEDIA: "自行提供的媒體",
    Channel.INTERFACE: "介面",
}
