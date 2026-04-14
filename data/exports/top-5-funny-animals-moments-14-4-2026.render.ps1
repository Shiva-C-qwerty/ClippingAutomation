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
$buildDir = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$clips = @(
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\remote_media_wwu7_e88\01_why-you-can-t-use-the-bathroom-right-now.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\01.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\remote_media_wwu7_e88\02_feeding-an-old-dog-vs-feeding-a-young-dog.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\02.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\remote_media_wwu7_e88\03_fool-me-twice-shame-on-me.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\03.mp4'
    Duration = 17
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\remote_media_wwu7_e88\04_baby-beaver-cleaning-his-belly.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\04.mp4'
    Duration = 18
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\remote_media_wwu7_e88\05_cat-make-a-perfect-ball.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\05.mp4'
    Duration = 10
  }
  @{
    Input = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\Extras\Outro.mp4'
    Output = 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\06.mp4'
    Duration = 4
  }
)

foreach ($clip in $clips) {
  if (Test-HasAudio -InputPath $clip.Input) {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -t $clip.Duration -filter_complex '[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:10[bg];[0:v]fps=30,scale=950:1689:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=59:y=109:w=962:h=1701:color=white@0.14:t=fill,drawbox=x=59:y=109:w=962:h=1701:color=white@0.08:t=6,setsar=1,format=yuv420p[vout]' -af "loudnorm=I=-16:LRA=11:TP=-1.5" -map [vout] -map 0:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  } else {
    Invoke-CheckedCommand { ffmpeg -y -i $clip.Input -f lavfi -t $clip.Duration -i anullsrc=channel_layout=stereo:sample_rate=48000 -filter_complex '[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:10[bg];[0:v]fps=30,scale=950:1689:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=59:y=109:w=962:h=1701:color=white@0.14:t=fill,drawbox=x=59:y=109:w=962:h=1701:color=white@0.08:t=6,setsar=1,format=yuv420p[vout]' -shortest -map [vout] -map 1:a:0 -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart -c:a aac -ar 48000 -b:a 192k $clip.Output }
  }
}

$concatLines = $clips | ForEach-Object {
  "file '$($_.Output.Replace('\', '/'))'"
}
[System.IO.File]::WriteAllLines('C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\concat.txt', $concatLines, [System.Text.UTF8Encoding]::new($false))
Invoke-CheckedCommand { ffmpeg -y -f concat -safe 0 -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\concat.txt' -vf format=yuv420p -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -ar 48000 -b:a 192k -movflags +faststart 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\combined.mp4' }
$overlayFilter = 'drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''Ranking The'':x=(w-text_w)/2:y=26:fontsize=42:fontcolor=white:borderw=3:bordercolor=black@0.82:shadowx=2:shadowy=3:shadowcolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''Best Animal Moments'':x=(w-text_w)/2:y=68:fontsize=54:fontcolor=0x3DFF57:borderw=3:bordercolor=black@0.85:shadowx=2:shadowy=3:shadowcolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''(BEST ONE LAST)'':x=(w-text_w)/2:y=124:fontsize=26:fontcolor=0xFFD84A:borderw=2:bordercolor=black@0.82:shadowx=2:shadowy=2:shadowcolor=black@0.45,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''1.'':x=58:y=360:fontsize=48:fontcolor=0xFFD84A@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''2.'':x=58:y=438:fontsize=48:fontcolor=0xAFAFAF@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''3.'':x=58:y=516:fontsize=48:fontcolor=0xFF4D4D@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''4.'':x=58:y=594:fontsize=48:fontcolor=0xFF9E3D@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''5.'':x=58:y=672:fontsize=48:fontcolor=0xFFFFFF@0.68:borderw=2:bordercolor=black@0.55,drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''5.'':x=52:y=668:fontsize=60:fontcolor=0xFFFFFF:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,0.000,18.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,0.000,0.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,0.000,0.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''4.'':x=52:y=590:fontsize=60:fontcolor=0xFF9E3D:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,18.000,36.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/top-5-funny-animals-moments-14-4-2026_build/overlay/title_02.txt'':reload=0:x=116:y=598:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,18.000,36.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,18.000,18.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,18.000,18.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''3.'':x=52:y=512:fontsize=60:fontcolor=0xFF4D4D:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,36.000,53.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/top-5-funny-animals-moments-14-4-2026_build/overlay/title_03.txt'':reload=0:x=116:y=520:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,36.000,53.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,36.000,36.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,36.000,36.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''2.'':x=52:y=434:fontsize=60:fontcolor=0xAFAFAF:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,53.000,71.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/top-5-funny-animals-moments-14-4-2026_build/overlay/title_04.txt'':reload=0:x=116:y=442:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,53.000,71.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,53.000,53.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,53.000,53.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''1.'':x=52:y=356:fontsize=60:fontcolor=0xFFD84A:borderw=3:bordercolor=black@0.75:shadowx=3:shadowy=3:shadowcolor=black@0.55:enable=''between(t,71.000,81.000)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':textfile=''C\:/Users/User/Desktop/Personal Project/ClippingAutomation/data/exports/top-5-funny-animals-moments-14-4-2026_build/overlay/title_05.txt'':reload=0:x=116:y=364:fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.65:shadowx=2:shadowy=2:shadowcolor=black@0.45:enable=''between(t,71.000,81.000)'',drawbox=x=0:y=0:w=iw:h=ih:color=white@0.10:t=fill:enable=''between(t,71.000,71.120)'',drawbox=x=0:y=166:w=iw:h=8:color=white@0.18:t=fill:enable=''between(t,71.000,71.120)'',drawtext=fontfile=''C\:/Windows/Fonts/arialbd.ttf'':text=''@clipbot demo'':x=(w-text_w)/2:y=h-38:fontsize=24:fontcolor=white@0.78:borderw=2:bordercolor=black@0.55'
Invoke-CheckedCommand { ffmpeg -y -i 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026_build\combined.mp4' -vf $overlayFilter -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a copy -movflags +faststart 'C:\Users\User\Desktop\Personal Project\ClippingAutomation\data\exports\top-5-funny-animals-moments-14-4-2026.mp4' }
