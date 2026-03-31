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
$buildDir = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\remote_media_n8y_83v3\01_guard-dog.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\01.mp4'
    Duration = 10
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\remote_media_n8y_83v3\02_dog-catches-its-own-reflection-in-the-phone-and-gets-completely.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\02.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\remote_media_n8y_83v3\03_dog-i-am-doing-it-leave-me-alone.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\03.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\remote_media_n8y_83v3\04_mom-cat-you-go-learn-today.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\04.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\remote_media_n8y_83v3\05_the-portal-is-now-open.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\05.mp4'
    Duration = 11
  }
)

foreach ($clip in $clips) {
  if (Test-HasAudio -InputPath $clip.Input) {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -t $clip.Duration -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" -af "loudnorm=I=-16:LRA=11:TP=-1.5" -map 0:v:0 -map 0:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  } else {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -f lavfi -t $clip.Duration -i anullsrc=channel_layout=stereo:sample_rate=48000 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" -shortest -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  }
}

$concatLines = $clips | ForEach-Object {
  "file '$($_.Output.Replace('\', '/'))'"
}
[System.IO.File]::WriteAllLines('C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\concat.txt', $concatLines, [System.Text.UTF8Encoding]::new($false))
Invoke-CheckedCommand { ffmpeg -y -f concat -safe 0 -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5_build\concat.txt' -vf format=yuv420p -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -ar 48000 -b:a 192k -movflags +faststart 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\animal-funny-top-5.mp4' }
