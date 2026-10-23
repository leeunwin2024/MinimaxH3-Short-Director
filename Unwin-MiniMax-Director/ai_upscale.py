"""Optional offline AI upscale with Real-ESRGAN NCNN Vulkan; no API calls."""
import os, shutil, subprocess, tempfile, threading, uuid, time, urllib.request, zipfile, hashlib
from pathlib import Path
from aiohttp import web
from server import PromptServer
from .nodes import safe_output, ffmpeg, run_ffmpeg

JOBS={}
INSTALL_JOBS={}
LOCK=threading.Lock()
RELEASE_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
MODELS=("realesrgan-x4plus", "realesrgan-x4plus-anime")

def binary():
    env=os.environ.get('UNWIN_REALESRGAN_EXE','')
    base=Path(__file__).resolve().parent
    options=[env,str(base/'tools'/'realesrgan-ncnn-vulkan.exe'),str(base/'tools'/'realesrgan-ncnn-vulkan'),shutil.which('realesrgan-ncnn-vulkan'),shutil.which('realesrgan-ncnn-vulkan.exe')]
    for item in options:
        if item and Path(item).is_file(): return str(Path(item).resolve())
    return None

def model_directory():
    return Path(__file__).resolve().parent/'tools'/'models'

def validate_install():
    exe=binary()
    root=model_directory()
    # Portable engine may also be supplied by PATH; model folder must be next to executable.
    if exe and (Path(exe).parent/'models').is_dir():root=Path(exe).parent/'models'
    missing=[f'{name}.{ext}' for name in MODELS for ext in ('param','bin') if not (root/f'{name}.{ext}').is_file() or (root/f'{name}.{ext}').stat().st_size==0]
    ready=bool(exe) and not missing
    message=('Ready: Real-ESRGAN executable and model pairs verified' if ready else ('Executable missing. ' if not exe else '')+('Missing model files: '+', '.join(missing) if missing else ''))
    return {'installed':bool(exe),'ready':ready,'executable':exe or '', 'models':list(MODELS),'models_dir':str(root),'missing':missing,'message':message}

def install_worker(job):
    try:
        base=Path(__file__).resolve().parent/'tools'
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='unwin_esrgan_') as tmp:
            archive=Path(tmp)/'realesrgan.zip'
            req=urllib.request.Request(RELEASE_URL,headers={'User-Agent':'Unwin-MiniMax-Director/1.1.1'})
            with urllib.request.urlopen(req,timeout=45) as source,archive.open('wb') as target:
                total=int(source.headers.get('Content-Length','0'))
                received=0
                while True:
                    chunk=source.read(1024*512)
                    if not chunk:break
                    received+=len(chunk)
                    if received>350*1024*1024:raise RuntimeError('Archive exceeds safety limit')
                    target.write(chunk)
                    with LOCK:INSTALL_JOBS[job].update(status=f'Downloading {received//1048576} MB',progress=min(75,int(received/total*75)) if total else 10)
            with zipfile.ZipFile(archive) as z:
                members=z.infolist()
                if sum(x.file_size for x in members)>700*1024*1024:raise RuntimeError('Archive expands beyond safety limit')
                wanted={x.filename.replace('\\','/').split('/')[-1]:x for x in members if not x.is_dir()}
                exe_name='realesrgan-ncnn-vulkan.exe' if os.name=='nt' else 'realesrgan-ncnn-vulkan'
                needed=[exe_name]+[f'{m}.{ext}' for m in MODELS for ext in ('param','bin')]
                for name in needed:
                    if name not in wanted:raise RuntimeError('Official archive is missing '+name)
                for i,name in enumerate(needed):
                    target_dir=base if name==exe_name else base/'models';target_dir.mkdir(parents=True,exist_ok=True)
                    temp_file=target_dir/(name+'.installing')
                    with z.open(wanted[name]) as source,temp_file.open('wb') as target:shutil.copyfileobj(source,target)
                    if not temp_file.stat().st_size:raise RuntimeError('Empty file: '+name)
                    temp_file.replace(target_dir/name)
                    with LOCK:INSTALL_JOBS[job].update(status='Installing '+name,progress=76+int((i+1)/len(needed)*20))
        result=validate_install()
        if not result['ready']:raise RuntimeError(result['message'])
        with LOCK:INSTALL_JOBS[job].update(status='Installed and verified',progress=100,done=True)
    except Exception as exc:
        with LOCK:INSTALL_JOBS[job].update(status='Installation failed',error=str(exc))

@PromptServer.instance.routes.post('/unwin/ai-upscale/install')
async def install_esrgan(request):
    with LOCK:
        if any(not j.get('done') and not j.get('error') for j in INSTALL_JOBS.values()):
            return web.json_response({'error':'An installation is already running'},status=409)
        job=uuid.uuid4().hex[:12]
        INSTALL_JOBS[job]={'job':job,'status':'Starting download','progress':0,'done':False,'error':''}
    threading.Thread(target=install_worker,args=(job,),daemon=True).start()
    return web.json_response({'job':job})

@PromptServer.instance.routes.get('/unwin/ai-upscale/install')
async def install_esrgan_status(request):
    job=request.query.get('job','')
    with LOCK: result=INSTALL_JOBS.get(job)
    if result is None:return web.json_response({'error':'Unknown installation'},status=404)
    return web.json_response(result)

def probe_duration(path):
    tool=shutil.which('ffprobe')
    if not tool: return None
    p=subprocess.run([tool,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],capture_output=True,text=True)
    try:return float(p.stdout.strip())
    except: return None

def update(job,**kw):
    with LOCK:JOBS[job].update(kw)

def _cancelled(job):
    with LOCK:
        return bool(JOBS.get(job, {}).get('cancel_requested'))


def _run_esrgan_batch(job, cmd, timeout_seconds=180):
    """Drain engine output and impose a hard timeout; don't leave a stuck Vulkan child running."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors='replace', bufsize=1,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = []
    def drain():
        try:
            for line in proc.stdout:
                lines.append(line.rstrip())
                if len(lines) > 120:
                    del lines[:60]
        except Exception as exc:
            lines.append('Log reader: ' + str(exc))
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    started = time.monotonic()
    try:
        while proc.poll() is None:
            if _cancelled(job):
                raise RuntimeError('Cancelled by user')
            if time.monotonic() - started > timeout_seconds:
                raise RuntimeError('Real-ESRGAN batch exceeded %ds. Last output: %s' %
                                   (timeout_seconds, ' | '.join(lines[-6:])))
            time.sleep(0.5)
        reader.join(timeout=3)
        if proc.returncode:
            raise RuntimeError('Real-ESRGAN exit %s: %s' %
                               (proc.returncode, ' | '.join(lines[-12:])))
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: pass
        raise
    return ' | '.join(lines[-6:])


def worker(job,src,scale,model):
    try:
        exe=binary()
        verification=validate_install()
        if not verification['ready']:
            raise RuntimeError(verification['message'])
        src=Path(src)
        # Cache allows retrying without reprocessing completed frames.
        fingerprint=hashlib.sha256(('%s|%s|%s|%s|%s' %
            (src.resolve(),src.stat().st_size,src.stat().st_mtime_ns,scale,model)).encode()).hexdigest()[:20]
        cache=src.parent/'unwin_ai_cache'/fingerprint
        frames=cache/'frames';outframes=cache/'upscaled'
        frames.mkdir(parents=True,exist_ok=True);outframes.mkdir(parents=True,exist_ok=True)
        update(job,status='Extracting frames (or reusing cached frames)',progress=3,cache=str(cache))
        if not (cache/'extraction_complete').exists():
            for old in frames.glob('frame_*.png'):old.unlink()
            try:
                run_ffmpeg(['-i',str(src),'-map','0:v:0','-an','-sn','-dn',
                            '-fps_mode','passthrough',frames/'frame_%08d.png'])
            except RuntimeError as exc:
                if 'fps_mode' not in str(exc) and 'Unrecognized option' not in str(exc):raise
                run_ffmpeg(['-i',str(src),'-map','0:v:0','-an','-sn','-dn',frames/'frame_%08d.png'])
            (cache/'extraction_complete').write_text('ok')
        inputs=sorted(frames.glob('frame_*.png'))
        count=len(inputs)
        if not count:raise RuntimeError('No frames extracted')
        # Files are processed in groups of 8, with retries at smaller Vulkan tile sizes.
        batch_size=8
        completed=0
        for start in range(0,count,batch_size):
            if _cancelled(job):raise RuntimeError('Cancelled by user')
            batch=inputs[start:start+batch_size]
            pending=[f for f in batch if not (outframes/f.name).is_file() or (outframes/f.name).stat().st_size==0]
            if pending:
                with tempfile.TemporaryDirectory(prefix='unwin_batch_',dir=str(cache)) as tmp:
                    batch_in=Path(tmp)/'input';batch_in.mkdir()
                    # Copy rather than symlink: works on Windows without administrator permissions.
                    for frame in pending:shutil.copy2(frame,batch_in/frame.name)
                    errors=[]
                    for tile in (128,64,32):
                        if _cancelled(job):raise RuntimeError('Cancelled by user')
                        cmd=[exe,'-i',str(batch_in),'-o',str(outframes),'-n',model,
                             '-s',str(scale),'-f','png','-g','0','-t',str(tile)]
                        update(job,status='AI enhancing frames %d-%d/%d (NVIDIA GPU 0, tile %d)' %
                               (start+1,start+len(batch),count,tile),
                               progress=min(89,10+int(completed/count*79)),
                               current_frame=completed,total_frames=count,gpu='NVIDIA GPU 0',tile=tile)
                        try:
                            log=_run_esrgan_batch(job,cmd,timeout_seconds=180)
                            missing=[f.name for f in pending if not (outframes/f.name).is_file() or (outframes/f.name).stat().st_size==0]
                            if missing:raise RuntimeError('No output for '+', '.join(missing[:3])+'. '+log)
                            break
                        except RuntimeError as exc:
                            errors.append('tile %d: %s' % (tile,str(exc)))
                            if 'Cancelled by user' in str(exc):raise
                            # Drop partial files from failed batch before retry.
                            for f in pending:
                                dest=outframes/f.name
                                if dest.exists():dest.unlink()
                    else:
                        raise RuntimeError('Batch %d-%d failed: %s' %
                                           (start+1,start+len(batch),' ; '.join(errors)[-1800:]))
            completed+=len(batch)
            elapsed=time.monotonic()-JOBS[job]['started_at']
            eta=int(elapsed/completed*(count-completed)) if completed else None
            update(job,status='AI enhancing frames: %d/%d' % (completed,count),
                   progress=min(89,10+int(completed/count*79)),current_frame=completed,
                   total_frames=count,eta_seconds=eta,elapsed_seconds=int(elapsed))
        update(job,status='Encoding enhanced video and preserving audio',progress=92)
        dest=safe_output('unwin_ai_upscaled_'+job+'.mp4',False)
        probe=shutil.which('ffprobe');fps='24'
        if probe:
            r=subprocess.run([probe,'-v','error','-select_streams','v:0',
                '-show_entries','stream=avg_frame_rate',
                '-of','default=noprint_wrappers=1:nokey=1',str(src)],capture_output=True,text=True)
            val=r.stdout.strip()
            if val and val!='0/0':fps=val
        run_ffmpeg(['-framerate',fps,'-i',outframes/'frame_%08d.png','-i',str(src),
                    '-map','0:v:0','-map','1:a?','-c:v','libx264','-preset','medium',
                    '-crf','17','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',
                    '-shortest',dest])
        update(job,status='Complete',progress=100,output=dest.name,eta_seconds=0)
    except Exception as e:
        update(job,status='Cancelled' if _cancelled(job) else 'Failed',error=str(e),progress=0)

@PromptServer.instance.routes.post('/unwin/ai-upscale/cancel')
async def ai_cancel(request):
    data=await request.json()
    job=str(data.get('job',''))
    with LOCK:
        if job not in JOBS:return web.json_response({'error':'Unknown job'},status=404)
        JOBS[job]['cancel_requested']=True
        JOBS[job]['status']='Cancelling...'
    return web.json_response({'job':job,'cancel_requested':True})

@PromptServer.instance.routes.get('/unwin/ai-upscale/status')
async def ai_status(request):
    job=request.query.get('job','')
    if job:
        with LOCK: d=JOBS.get(job)
        if d is None:return web.json_response({'error':'Unknown job'},status=404)
        return web.json_response(d)
    exe=binary()
    return web.json_response(validate_install())

@PromptServer.instance.routes.post('/unwin/ai-upscale/start')
async def ai_start(request):
    try:
        data=await request.json();src=safe_output(data.get('filename',''))
        if src.suffix.lower() not in ('.mp4','.mov','.mkv','.webm'):raise ValueError('Select a supported video')
        if not validate_install()['ready']:raise RuntimeError(validate_install()['message'])
        model=data.get('model','realesrgan-x4plus')
        if model not in ('realesrgan-x4plus','realesrgan-x4plus-anime'):raise ValueError('Invalid model')
        scale=int(data.get('scale',2))
        if scale not in (2,4):raise ValueError('Scale must be 2 or 4')
        job=uuid.uuid4().hex[:12]
        with LOCK:JOBS[job]={'job':job,'status':'Queued','progress':0,'output':'','error':'','cancel_requested':False,'started_at':time.monotonic()}
        threading.Thread(target=worker,args=(job,src,scale,model),daemon=True).start()
        return web.json_response({'job':job})
    except Exception as e:return web.json_response({'error':str(e)},status=400)