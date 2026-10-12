"""Offline batch matte worker run using an existing SD Python environment."""
from pathlib import Path
import json,os,sys

def main():
 manifest=Path(sys.argv[1]).resolve();data=json.loads(manifest.read_text(encoding='utf-8'));root=manifest.parent
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_MODULES_CACHE=str(root/'rmbg-module-cache'))
 import torch
 from torchvision import transforms
 from transformers import AutoModelForImageSegmentation
 from PIL import Image
 torch.set_num_threads(6)
 folder=Path(data['model']).resolve()
 if not (folder/'model.safetensors').is_file() or not (folder/'config.json').is_file():raise ValueError('本機 RMBG 模型不完整')
 model=AutoModelForImageSegmentation.from_pretrained(str(folder),trust_remote_code=True,local_files_only=True,use_safetensors=True,bb_pretrained=False).eval().to(data['device'])
 transform=transforms.Compose([transforms.Resize((data['resolution'],data['resolution'])),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
 if len(data['files'])>32:raise ValueError('去背批次過大')
 for row in data['files']:
  source=Path(row['input']).resolve();target=Path(row['output']).resolve()
  if not source.is_relative_to(root) or not target.is_relative_to(root):raise ValueError('去背檔案超出任務目錄')
  if target.is_file():continue
  image=Image.open(source).convert('RGB')
  if max(image.size)>4096:raise ValueError('去背圖片過大')
  with torch.inference_mode():mask=model(transform(image).unsqueeze(0).to(data['device']))[-1].sigmoid().cpu()
  alpha=transforms.ToPILImage()(mask[0].squeeze()).resize(image.size,Image.Resampling.LANCZOS)
  # Remove very faint halos while preserving the smooth edge and pale clothes.
  alpha=alpha.point(lambda x:0 if x<8 else 255 if x>247 else x);image.putalpha(alpha)
  temporary=target.with_suffix('.tmp.png');image.save(temporary);os.replace(temporary,target)
  print(json.dumps({'ready':target.name}),flush=True)

if __name__=='__main__':main()
