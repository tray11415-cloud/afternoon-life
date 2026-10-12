param([ValidateSet('reForge','ComfyUI')][string]$Backend='reForge')
$ErrorActionPreference='Stop'
if($Backend -eq 'reForge'){
 $sdRoot='D:\stable-diffusion-webui-reForge';$pythonPath=Join-Path $sdRoot 'venv\Scripts\python.exe'
 $scriptPath=Join-Path $sdRoot 'launch.py';$scriptArg='"'+$scriptPath+'"';$sdArguments=@('-X','utf8',$scriptArg,'--api','--port','7861','--server-name','127.0.0.1','--skip-prepare-environment','--skip-install','--no-gradio-queue');$statusUrl='http://127.0.0.1:7861/sdapi/v1/samplers'
}else{
 $sdRoot='D:\ComfyUI_windows_portable_nightly_pytorch\ComfyUI';$pythonPath='D:\ComfyUI_windows_portable_nightly_pytorch\python_embeded\python.exe'
 $scriptPath=Join-Path $sdRoot 'main.py';$scriptArg='"'+$scriptPath+'"';$sdArguments=@('-X','utf8',$scriptArg,'--listen','127.0.0.1','--port','8188','--disable-auto-launch','--disable-xformers','--use-pytorch-cross-attention');$statusUrl='http://127.0.0.1:8188/system_stats'
}
if(-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $scriptPath)){throw '找不到既有 SD 安裝。請在遊戲設定頁重新選擇資料夾。'}
try{ $ready=Invoke-RestMethod -Uri $statusUrl -TimeoutSec 2; if($ready){Write-Output 'SD 已在執行，可直接在遊戲設定測試連線。';exit 0} }catch{}
$logRoot=Join-Path (Split-Path -Parent $PSScriptRoot) 'work';New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$sdProcess=Start-Process -FilePath $pythonPath -ArgumentList $sdArguments -WorkingDirectory $sdRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot ('sd-'+$Backend+'.log')) -RedirectStandardError (Join-Path $logRoot ('sd-'+$Backend+'-error.log')) -PassThru
Write-Output ('SD 已在背景啟動，請到遊戲生圖設定測試連線。PID: '+$sdProcess.Id)
