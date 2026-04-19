$ErrorActionPreference = 'Stop'
function Invoke-CheckedCommand {
  param([scriptblock]$Command)
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "External command failed with exit code $LASTEXITCODE"
  }
}
function Test-HasAudio {
  param([string]$InputPath)
  $audioProbe = & ffprobe -v error -select_streams a:0 -show_entries stream=index -of csv=p=0 $InputPath
  if ($LASTEXITCODE -ne 0) {
    throw "ffprobe failed while checking audio for $InputPath"
  }
  return -not [string]::IsNullOrWhiteSpace(($audioProbe | Out-String).Trim())
}
$buildDir = 'data\exports\audio-bed-render-smoke\build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\audio-bed-prototype\clip_617_boop_source.mp4'
    Output = 'data\exports\audio-bed-render-smoke\build\01.mp4'
    Duration = 5
    AudioBed = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\assets\audio_beds\Sakura-Girl-Tiny-Paws-chosic.mp3'
  }
)

foreach ($clip in $clips) {
  if (Test-HasAudio -InputPath $clip.Input) {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -t $clip.Duration -filter_complex '[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:10[bg];[0:v]fps=30,scale=950:1689:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=59:y=109:w=962:h=1701:color=white@0.14:t=fill,drawbox=x=59:y=109:w=962:h=1701:color=white@0.08:t=6,setsar=1,format=yuv420p[vout]' -af "loudnorm=I=-16:LRA=11:TP=-1.5" -map [vout] -map 0:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  } elseif ($clip.AudioBed) {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -stream_loop -1 -i $clip.AudioBed -t $clip.Duration -filter_complex '[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:10[bg];[0:v]fps=30,scale=950:1689:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=59:y=109:w=962:h=1701:color=white@0.14:t=fill,drawbox=x=59:y=109:w=962:h=1701:color=white@0.08:t=6,setsar=1,format=yuv420p[vout];[1:a]volume=0.18[aout]' -map [vout] -map [aout] -shortest -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  } else {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -f lavfi -t $clip.Duration -i anullsrc=channel_layout=stereo:sample_rate=48000 -filter_complex '[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:10[bg];[0:v]fps=30,scale=950:1689:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=59:y=109:w=962:h=1701:color=white@0.14:t=fill,drawbox=x=59:y=109:w=962:h=1701:color=white@0.08:t=6,setsar=1,format=yuv420p[vout]' -shortest -map [vout] -map 1:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  }
}

$concatLines = $clips | ForEach-Object {
  "file '$($_.Output.Replace('\', '/'))'"
}
[System.IO.File]::WriteAllLines('data\exports\audio-bed-render-smoke\build\concat.txt', $concatLines, [System.Text.UTF8Encoding]::new($false))
Invoke-CheckedCommand { ffmpeg -y -f concat -safe 0 -i 'data\exports\audio-bed-render-smoke\build\concat.txt' -vf format=yuv420p -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -ar 48000 -b:a 192k -movflags +faststart 'data\exports\audio-bed-render-smoke\build\combined.mp4' }
Copy-Item -LiteralPath 'data\exports\audio-bed-render-smoke\build\combined.mp4' -Destination 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\audio-bed-render-smoke\smoke.mp4' -Force
