#!/bin/bash
# Steps 2-5: trim chosen moment, reformat 16:9 -> 9:16 (facecam top / gameplay bottom),
# caption with opus-style ASS, render final master.
set -e
cd /tmp/clipify
START=20.6
DUR=18.6

# Step 2: frame-accurate trim (re-encode; -c copy would snap to keyframes)
ffmpeg -y -loglevel error -ss $START -t $DUR -i source_vod.mp4 \
  -c:v libx264 -preset ultrafast -crf 20 -c:a aac clip_1.mp4

# Step 4: vertical 1080x1920 = facecam (top 1080x608) + gameplay (bottom 1080x1312)
# facecam ROI in source: 420x236 at (24,24). gameplay: center crop 889x1080.
ffmpeg -y -loglevel error -i clip_1.mp4 -filter_complex "
[0:v]split=2[c][g];
[c]crop=420:236:24:24,scale=1080:608:flags=lanczos[cam];
[g]crop=889:1080:515:0,scale=1080:1312:flags=lanczos[game];
[cam][game]vstack[v]" \
  -map "[v]" -map 0:a -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p -c:a aac clip_1_vertical.mp4

# Step 5: re-transcribe trimmed clip for clip-relative word timestamps
ffmpeg -y -loglevel error -i clip_1.mp4 -vn -ac 1 -ar 16000 clip_1.wav
python3 ps_transcribe.py clip_1.wav clip_1_words.json > /dev/null 2>&1
python3 /home/user/.claude/skills/clipify/scripts/build_ass.py clip_1_words.json captions.ass opus

mkdir -p out
ffmpeg -y -loglevel error -i clip_1_vertical.mp4 -vf "subtitles=captions.ass" \
  -c:v libx264 -preset fast -crf 20 -c:a copy out/clip_1_final.mp4
ffprobe -v error -show_entries format=duration,size -of default=nw=1 out/clip_1_final.mp4
ffprobe -v error -select_streams v -show_entries stream=width,height -of csv=p=0 out/clip_1_final.mp4
