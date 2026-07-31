"""Pipeline configuration.

Everything tunable lives here so detector experiments don't require code edits.
Load order: defaults -> optional TOML file -> environment variables (CLIPENGINE_*).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields


@dataclass
class DetectConfig:
    # signal weights for fusion (normalised series are combined linearly)
    weight_chat_velocity: float = 1.0
    weight_chat_emotes: float = 0.8
    weight_audio_energy: float = 0.7
    # emote tokens counted as hype/laughter reactions
    emote_tokens: list[str] = field(
        default_factory=lambda: [
            "LUL", "LULW", "OMEGALUL", "KEKW", "PogChamp", "Pog", "POGGERS",
            "monkaS", "WutFace", "widepeepoHappy", "Sadge", "ICANT", "CAUGHT",
        ]
    )
    # candidate windows
    target_duration: float = 75.0  # >60s: TikTok Creator Rewards pays only on >1min videos
    min_gap: float = 30.0          # non-overlap spacing between candidates
    top_n: int = 8
    pre_roll: float = 8.0          # context lead-in before the detected peak


@dataclass
class EditConfig:
    out_width: int = 1080
    out_height: int = 1920
    facecam_tile_height: int = 608  # facecam-top / gameplay-bottom layout
    crf: int = 20
    preset: str = "fast"


@dataclass
class CaptionConfig:
    style: str = "opus"  # opus | karaoke | minimal
    chunk_words: int = 3
    font: str = "Arial Black"
    font_size: int = 100
    highlight_colour: str = "&H0000FFFF&"  # ASS BGR: yellow


@dataclass
class TwitchConfig:
    client_id: str = ""
    client_secret: str = ""


@dataclass
class YouTubeConfig:
    client_id: str = ""
    client_secret: str = ""
    token_file: str = os.path.expanduser("~/.clipengine/youtube_tokens.json")
    redirect_uri: str = "http://localhost:8080"


@dataclass
class TikTokConfig:
    client_key: str = ""
    client_secret: str = ""
    token_file: str = os.path.expanduser("~/.clipengine/tiktok_tokens.json")
    redirect_uri: str = "http://localhost:8080"
    privacy_level: str = "SELF_ONLY"  # only option until the app passes audit


@dataclass
class ScheduleConfig:
    queue_db: str = os.path.expanduser("~/.clipengine/queue.db")
    windows: list[str] = field(default_factory=lambda: ["11:00-14:00", "17:00-22:00"])
    min_spacing_hours: float = 3.0
    daily_cap: int = 4
    tz: str = "UTC"


@dataclass
class AnalyticsConfig:
    stats_db: str = os.path.expanduser("~/.clipengine/stats.db")


@dataclass
class Config:
    detect: DetectConfig = field(default_factory=DetectConfig)
    edit: EditConfig = field(default_factory=EditConfig)
    caption: CaptionConfig = field(default_factory=CaptionConfig)
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    tiktok: TikTokConfig = field(default_factory=TikTokConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    work_dir: str = "/tmp/clipengine"
    roster_db: str = os.path.expanduser("~/.clipengine/roster.db")


def load(path: str | None = None) -> Config:
    cfg = Config()
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for section_field in fields(cfg):
            section = getattr(cfg, section_field.name)
            values = data.get(section_field.name)
            if isinstance(values, dict) and hasattr(section, "__dataclass_fields__"):
                for k, v in values.items():
                    if hasattr(section, k):
                        setattr(section, k, v)
            elif values is not None and not hasattr(section, "__dataclass_fields__"):
                setattr(cfg, section_field.name, values)
    # env overrides for secrets
    env = os.environ.get
    cfg.twitch.client_id = env("CLIPENGINE_TWITCH_CLIENT_ID", cfg.twitch.client_id)
    cfg.twitch.client_secret = env("CLIPENGINE_TWITCH_CLIENT_SECRET", cfg.twitch.client_secret)
    cfg.youtube.client_id = env("CLIPENGINE_YT_CLIENT_ID", cfg.youtube.client_id)
    cfg.youtube.client_secret = env("CLIPENGINE_YT_CLIENT_SECRET", cfg.youtube.client_secret)
    cfg.tiktok.client_key = env("CLIPENGINE_TT_CLIENT_KEY", cfg.tiktok.client_key)
    cfg.tiktok.client_secret = env("CLIPENGINE_TT_CLIENT_SECRET", cfg.tiktok.client_secret)
    return cfg
