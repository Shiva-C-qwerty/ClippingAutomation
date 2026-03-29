$ErrorActionPreference = 'Stop'
$buildDir = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\remote_media_l9ophfn_\01_bro-s-laughing-with-his-soul.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\01.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\remote_media_l9ophfn_\02_cat-slam.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\02.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\remote_media_l9ophfn_\03_trick-with-cigarette.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\03.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\remote_media_l9ophfn_\04_the-girls-laugh.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\04.mp4'
    Duration = 9
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\remote_media_l9ophfn_\05_so-thats-why-my-package-was-delayed.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\05.mp4'
    Duration = 9
  }
)

foreach ($clip in $clips) {
  & ffmpeg -y -i $clip.Input -t $clip.Duration -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" -af "loudnorm=I=-16:LRA=11:TP=-1.5" -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 192k $clip.Output
}

$concatLines = $clips | ForEach-Object {
  "file '$($_.Output.Replace('\', '/'))'"
}
Set-Content -Path 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\concat.txt' -Value $concatLines -Encoding utf8
& ffmpeg -y -f concat -safe 0 -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29_build\concat.txt' -c copy 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top5-2026-03-29.mp4'
