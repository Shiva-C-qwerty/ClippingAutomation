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
$buildDir = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\remote_media_39zlnoae\01_parrots-rehearsal.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\01.mp4'
    Duration = 10
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\remote_media_39zlnoae\02_he-swears-it-looked-like-something-dangerous.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\02.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\remote_media_39zlnoae\03_family-of-wild-boars-stroll-around-the-city.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\03.mp4'
    Duration = 15
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\remote_media_39zlnoae\04_quiet-human.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\04.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\remote_media_39zlnoae\05_he-only-drops-his-stick-for-one-reason.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\05.mp4'
    Duration = 15
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
[System.IO.File]::WriteAllLines('C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\concat.txt', $concatLines, [System.Text.UTF8Encoding]::new($false))
Invoke-CheckedCommand { ffmpeg -y -f concat -safe 0 -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\concat.txt' -vf format=yuv420p -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -ar 48000 -b:a 192k -movflags +faststart 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\combined.mp4' }
$overlayFilter = 'drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''Ranking The'':x=(w-text_w)/2:y=26:fontsize=42:fontcolor=white:borderw=3:bordercolor=black@0.82:shadowx=2:shadowy=3:shadowcolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''Best Animal Moments'':x=(w-text_w)/2:y=68:fontsize=54:fontcolor=0x3DFF57:borderw=3:bordercolor=black@0.85:shadowx=2:shadowy=3:shadowcolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''(BEST ONE LAST)'':x=(w-text_w)/2:y=124:fontsize=26:fontcolor=0xFFD84A:borderw=2:bordercolor=black@0.82:shadowx=2:shadowy=2:shadowcolor=black@0.45,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''1.'':x=58:y=360:fontsize=48:fontcolor=0xFFD84A@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''2.'':x=58:y=438:fontsize=48:fontcolor=0xAFAFAF@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''3.'':x=58:y=516:fontsize=48:fontcolor=0xFF4D4D@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''4.'':x=58:y=594:fontsize=48:fontcolor=0xFF9E3D@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''5.'':x=58:y=672:fontsize=48:fontcolor=0xFFFFFF@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''5.'':x=52:y=668:fontsize=60:fontcolor=0xFFFFFF:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,0.000,10.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/funny-top5-01-04-2026_build/overlay/title_01.txt'':reload=0:x=116:y=676:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,0.000,10.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,0.000,0.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,0.000,0.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''4.'':x=52:y=590:fontsize=60:fontcolor=0xFF9E3D:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,10.000,28.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/funny-top5-01-04-2026_build/overlay/title_02.txt'':reload=0:x=116:y=598:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,10.000,28.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,10.000,10.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,10.000,10.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''3.'':x=52:y=512:fontsize=60:fontcolor=0xFF4D4D:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,28.000,43.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/funny-top5-01-04-2026_build/overlay/title_03.txt'':reload=0:x=116:y=520:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,28.000,43.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,28.000,28.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,28.000,28.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''2.'':x=52:y=434:fontsize=60:fontcolor=0xAFAFAF:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,43.000,61.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/funny-top5-01-04-2026_build/overlay/title_04.txt'':reload=0:x=116:y=442:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,43.000,61.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,43.000,43.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,43.000,43.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''1.'':x=52:y=356:fontsize=60:fontcolor=0xFFD84A:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,61.000,76.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/funny-top5-01-04-2026_build/overlay/title_05.txt'':reload=0:x=116:y=364:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,61.000,76.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,61.000,61.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,61.000,61.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''@clipbot demo'':x=(w-text_w)/2:y=h-38:fontsize=24:fontcolor=white@0.78:borderw=2:bordercolor=black@0.55'
Invoke-CheckedCommand { ffmpeg -y -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026_build\combined.mp4' -vf $overlayFilter -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a copy -movflags +faststart 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\funny-top5-01-04-2026.mp4' }
