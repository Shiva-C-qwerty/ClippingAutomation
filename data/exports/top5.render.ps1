$ErrorActionPreference = 'Stop'
function Invoke-CheckedCommand {
  param([scriptblock]$Command)
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "External command failed with exit code $LASTEXITCODE"
  }
}
$buildDir = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\remote_media_587srgvr\01_bro-s-laughing-with-his-soul.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\01.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\remote_media_587srgvr\02_cat-slam.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\02.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\remote_media_587srgvr\03_trick-with-cigarette.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\03.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\remote_media_587srgvr\04_the-girls-laugh.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\04.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\remote_media_587srgvr\05_so-thats-why-my-package-was-delayed.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\05.mp4'
    Duration = 9
  }
)

foreach ($clip in $clips) {
  Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -t $clip.Duration -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" -af "loudnorm=I=-16:LRA=11:TP=-1.5" -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 192k $clip.Output }
}

$concatLines = $clips | ForEach-Object {
  "file '$($_.Output.Replace('\', '/'))'"
}
[System.IO.File]::WriteAllLines('C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\concat.txt', $concatLines, [System.Text.UTF8Encoding]::new($false))
Invoke-CheckedCommand { ffmpeg -y -f concat -safe 0 -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5_build\concat.txt' -c copy 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5.mp4' }
