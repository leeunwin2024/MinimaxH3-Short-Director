"""Allowlisted, local ComfyUI model downloads. Only user-triggered downloads use network."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import uuid

CATALOG = [
 ('h3_fl2v_fp8','Diffusion','minimax_h3_fl2va_pruned_fp8_scaled.safetensors','diffusion_models','Comfy-Org/MiniMax-H3','diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors','MiniMax H3 FL2VA pruned FP8. Suitable as a lower-storage choice; VRAM not guaranteed.','fl2va'),
 ('h3_fl2v_int8','Diffusion','minimax_h3_fl2va_pruned_int8_convrot.safetensors','diffusion_models','Comfy-Org/MiniMax-H3','diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors','MiniMax H3 FL2VA pruned INT8; requires compatible PyTorch/CUDA environment.','fl2va'),
 ('h3_text_nvfp4','Text encoder','qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors','text_encoders','Comfy-Org/MiniMax-H3','text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors','Required H3-specific 32B Qwen3-VL encoder; not interchangeable with generic 4B encoder.','h3'),
 ('h3_text_int8','Text encoder','qwen3vl_32b_minimax_h3_int8_convrot.safetensors','text_encoders','Comfy-Org/MiniMax-H3','text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors','H3-specific 32B Qwen3-VL INT8; higher memory and storage requirements.','h3'),
 ('h3_video_vae','Video VAE','minimax_h3_video_vae_fp16.safetensors','vae','Comfy-Org/MiniMax-H3','vae/minimax_h3_video_vae_fp16.safetensors','MiniMax H3 video VAE.','h3'),
 ('h3_audio_vae','Audio VAE','minimax_h3_audio_vae_fp32.safetensors','vae','Comfy-Org/MiniMax-H3','vae/minimax_h3_audio_vae_fp32.safetensors','MiniMax H3 audio VAE.','h3'),
 ('h3_turbo_v4_ema','LoRA','minimax_h3_turbo_v4_step600_ema.safetensors','loras','larryvrh/MiniMax-H3-Turbo-Lora','minimax_h3_turbo_v4_step600_ema.safetensors','H3 Turbo v4 EMA; author recommends 6–8 steps; heavy motion at 4 steps may smear.','h3'),
 ('h3_turbo_v4','LoRA','minimax_h3_turbo_v4_step600.safetensors','loras','larryvrh/MiniMax-H3-Turbo-Lora','minimax_h3_turbo_v4_step600.safetensors','H3 Turbo v4 non-EMA; comparison variant.','h3'),
]
REGISTRY = {x[0]:dict(id=x[0],category=x[1],filename=x[2],folder=x[3],repo=x[4],repo_path=x[5],description=x[6],family=x[7],url=f'https://huggingface.co/{x[4]}/resolve/main/{x[5]}') for x in CATALOG}
# SHA-256 published on the Hugging Face file page for this exact model.
REGISTRY['h3_turbo_v4']['sha256']='6c280b58f03b5dc89e791347679b821b8a85615bedae04d3c65bbbe753e07ce8'
_jobs={};_lock=threading.Lock()

def _path(item):
    import folder_paths
    existing=folder_paths.get_full_path(item['folder'],item['filename'])
    if existing and Path(existing).is_file():return Path(existing)
    roots=folder_paths.get_folder_paths(item['folder'])
    if not roots:raise RuntimeError('No ComfyUI model folder: '+item['folder'])
    root=Path(roots[0]).resolve();p=(root/item['filename']).resolve()
    if p.parent!=root:raise ValueError('Invalid model path')
    return p

def catalog():
    result=[]
    for item in REGISTRY.values():
        x=dict(item)
        try:
            p=_path(item);x['installed']=p.is_file();x['size_bytes']=p.stat().st_size if p.is_file() else 0
            x['location']=str(p)
        except Exception as e:x['installed']=False;x['error']=str(e)
        x['verification']='sha256 available' if item.get('sha256') else 'size and safetensors header (SHA-256 not published in registry)'
        result.append(x)
    return result

def _header_check(path):
    with open(path,'rb') as f:
        n=int.from_bytes(f.read(8),'little')
        if not 2<n<100_000_000:raise ValueError('Invalid safetensors header size')
        h=json.loads(f.read(n))
        if not isinstance(h,dict) or not any(k!='__metadata__' for k in h):raise ValueError('Invalid safetensors metadata')

def verify(model_id, full_hash=False):
    item=REGISTRY[model_id];p=_path(item)
    if not p.is_file():return {'installed':False,'valid':False,'reason':'File missing'}
    _header_check(p)
    sha=None
    if full_hash and item.get('sha256'):
        digest=hashlib.sha256()
        with open(p,'rb') as f:
            for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
        sha=digest.hexdigest()
        if sha!=item['sha256']:raise ValueError('SHA-256 checksum mismatch')
    return {'installed':True,'valid':True,'size_bytes':p.stat().st_size,'sha256':sha,'hash_verified':bool(sha),'path':str(p)}

def _run(job_id,model_id):
    job=_jobs[job_id];item=REGISTRY[model_id];part=None
    try:
        dest=_path(item);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise FileExistsError('Model already installed; verify instead')
        part=dest.with_name(dest.name+'.unwin-download-'+job_id+'.part')
        req=urllib.request.Request(item['url'],headers={'User-Agent':'Unwin-MiniMax-Director/1.0'})
        with urllib.request.urlopen(req,timeout=45) as response,open(part,'wb') as out:
            final_url=response.geturl()
            if not final_url.startswith('https://'):raise RuntimeError('Download redirected outside HTTPS')
            total=int(response.headers.get('Content-Length') or 0)
            job.update(status='downloading',total=total)
            while True:
                data=response.read(1024*1024)
                if not data:break
                out.write(data);job['downloaded']+=len(data)
        job['status']='verifying';_header_check(part)
        if item.get('sha256'):
            digest=hashlib.sha256()
            with open(part,'rb') as f:
                for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
            if digest.hexdigest()!=item['sha256']:raise ValueError('SHA-256 mismatch; refusing installation')
            job['hash_verified']=True
        if dest.exists():raise FileExistsError('Destination appeared during download')
        os.replace(part,dest);job['status']='installed'
    except Exception as e:job.update(status='failed',error=str(e))
    finally:
        if part and part.exists():part.unlink(missing_ok=True)

def start(model_id):
    if model_id not in REGISTRY:raise ValueError('Model is not in verified-source registry')
    if _path(REGISTRY[model_id]).exists():raise FileExistsError('Already installed')
    with _lock:
        if any(x['model_id']==model_id and x['status'] in ('queued','downloading','verifying') for x in _jobs.values()):raise RuntimeError('Download already running')
        jid=uuid.uuid4().hex[:12];_jobs[jid]=dict(id=jid,model_id=model_id,status='queued',downloaded=0,total=0,error='',hash_verified=False,started=time.time())
    threading.Thread(target=_run,args=(jid,model_id),daemon=True).start()
    return dict(_jobs[jid])

def jobs():return list(_jobs.values())[-30:]