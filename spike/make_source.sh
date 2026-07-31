#!/bin/bash
# Build a mock 'stream VOD' : espeak streamer voice + animated 'gameplay' + facecam box
set -e
cd /tmp/clipify
mkdir -p seg

say() { espeak-ng -v en-us -s "$3" -p "$4" -w "seg/$1.wav" "$2"; }

# ~90s of mock stream dialogue. The 'funny spike' is the ward/dragon fail ~ mid-video.
say 01 "Okay chat we are back in ranked. Today is the day we finally hit diamond. I can feel it." 160 40
say 02 "So the plan is simple. We farm safely, we do not take any silly fights, and we scale into the late game." 160 40
say 03 "I am just going to place this ward in the bush. Standard stuff. Nothing can go wrong here." 155 40
say 04 "Wait. Wait wait wait. Why is the whole enemy team in this bush. WHY IS THE WHOLE TEAM HERE." 195 60
say 05 "NO NO NO NO. I clicked the wrong button. I just flashed INTO them. I flashed into five people chat." 210 70
say 06 "And I am dead. Of course I am dead. That was the greatest ward of all time. Clip that. Actually do not clip that." 170 45
say 07 "You know what, that was strategy. I was checking if their cooldowns work. They do. Very useful information." 160 42
say 08 "Okay we are respawning. New plan. We pretend that never happened and we never speak of it again." 160 40
say 09 "The team just pinged the dragon. Fine. We will do the dragon. What could possibly go wrong at the dragon." 158 40
say 10 "I have literally been dead for ten seconds and they started the dragon anyway. This team is incredible." 165 45

# concat with short pauses
rm -f seg/list.txt
for i in 01 02 03 04 05 06 07 08 09 10; do
  echo "file '$i.wav'" >> seg/list.txt
  ffmpeg -y -loglevel error -f lavfi -i anullsrc=r=22050:cl=mono -t 0.7 "seg/p$i.wav"
  echo "file 'p$i.wav'" >> seg/list.txt
done
ffmpeg -y -loglevel error -f concat -safe 0 -i seg/list.txt -ar 16000 -ac 1 voice.wav
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 voice.wav)
echo "voice duration: $DUR"

# 1920x1080 'stream layout': mandelbrot zoom = gameplay, top-left box = facecam
ffmpeg -y -loglevel error \
  -f lavfi -i "mandelbrot=size=1920x1080:rate=30" \
  -f lavfi -i "testsrc2=size=420x236:rate=30" \
  -i voice.wav \
  -filter_complex "[1:v]drawtext=text='FACECAM':fontsize=36:fontcolor=white:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=black@0.5[cam];[0:v][cam]overlay=24:24,drawtext=text='mock stream - pipeline trial':fontsize=28:fontcolor=white@0.7:x=24:y=h-44[v]" \
  -map "[v]" -map 2:a -t "$DUR" -c:v libx264 -preset ultrafast -crf 26 -pix_fmt yuv420p -c:a aac source_vod.mp4
ffprobe -v error -show_entries format=duration,size -of default=nw=1 source_vod.mp4
