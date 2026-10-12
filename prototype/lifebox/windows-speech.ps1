$ErrorActionPreference='Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName System.Speech
$speech=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
 $request=[Console]::In.ReadToEnd() | ConvertFrom-Json
 if($request.operation -eq 'voices') {
  $voices=@($speech.GetInstalledVoices() | Where-Object Enabled | ForEach-Object { @{id=$_.VoiceInfo.Name;name=$_.VoiceInfo.Name;lang=$_.VoiceInfo.Culture.Name} })
  @{voices=$voices} | ConvertTo-Json -Depth 4 -Compress
 } elseif($request.operation -eq 'render') {
  $speech.SelectVoice([string]$request.voice)
  $speech.Rate=[int]$request.rate
  $speech.Volume=100
  $speech.SetOutputToWaveFile([string]$request.output)
  $speech.Speak([string]$request.text)
  $speech.SetOutputToNull()
 } else { throw 'Unknown operation' }
} finally { $speech.Dispose() }
