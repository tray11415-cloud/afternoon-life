param([switch]$Demo,[int]$Port=8765)
$ErrorActionPreference='Stop'
$prototypeRoot=$PSScriptRoot;$projectRoot=Split-Path -Parent $prototypeRoot
$bundledPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$runtimeArguments=@()
if(Test-Path -LiteralPath $bundledPython){$pythonRuntime=$bundledPython}
elseif(Get-Command py -ErrorAction SilentlyContinue){$pythonRuntime=(Get-Command py).Source;$runtimeArguments=@('-3')}
elseif(Get-Command python -ErrorAction SilentlyContinue){$pythonRuntime=(Get-Command python).Source}
else{throw 'Python 3.12+ is required. Install Python, then run: python -m pip install -r prototype/requirements.txt'}
$workRoot=Join-Path $projectRoot 'work';New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$pidFile=Join-Path $workRoot ('play-server'+$(if($Port -ne 8765){'-'+$Port}else{''})+'.pid')
if(Test-Path -LiteralPath $pidFile){
 $existingId=[int](Get-Content -LiteralPath $pidFile);$existingProcess=Get-Process -Id $existingId -ErrorAction SilentlyContinue
 if($existingProcess){$info=Get-CimInstance Win32_Process -Filter "ProcessId=$existingId";if($info.CommandLine -match ('lifebox.play.*--port '+$Port+'\b')){Write-Output ('Game is running: http://127.0.0.1:'+$Port);exit 0}}
}
$arguments=$runtimeArguments+@('-X','utf8','-B','-m','lifebox.play','--port',[string]$Port)
if($Demo){$arguments+=@('--demo')}
$serverProcess=Start-Process -FilePath $pythonRuntime -ArgumentList $arguments -WorkingDirectory $prototypeRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $workRoot 'play-server.log') -RedirectStandardError (Join-Path $workRoot 'play-server-error.log') -PassThru
[System.IO.File]::WriteAllText($pidFile,[string]$serverProcess.Id)
Write-Output ('Starting game: http://127.0.0.1:'+$Port)
