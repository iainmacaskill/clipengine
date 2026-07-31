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
class Config:
    detect: DetectConfig = field(default_factory=DetectConfig)
    edit: EditConfig = field(default_factory=EditConfig)
    caption: CaptionConfig = field(default_factory=CaptionConfig)
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
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
    cfg.twitch.client_id = os.environ.get("CLIPENGINE_TWITCH_CLIENT_ID", cfg.twitch.client_id)
    cfg.twitch.client_secret = os.environ.get(
        "CLIPENGINE_TWITCH_CLIENT_SECRET", cfg.twitch.client_secret
    )
    return cfg
