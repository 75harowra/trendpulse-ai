import os
import json
import math
import re
import html
import hashlib
import requests
import subprocess
import tempfile
import textwrap
import unicodedata
from pathlib import Path

VERSION = '4.2'
API_KEY = os.getenv('PIXABAY_API_KEY')
WIDTH, HEIGHT, FPS = 1920, 1080, 25
SCENE_TIME, MAX_MEDIA = 5, 32
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
output = Path('videos')
output.mkdir(exist_ok=True)
session = requests.Session()
session.headers.update({'User-Agent': 'TrendPulseGlobal/4.2'})
cache = {}

def run(cmd):
    subprocess.run(cmd, check=True)

def ffmpeg(args):
    run(['ffmpeg','-y','-hide_banner','-loglevel','error',
         '-filter_threads','2','-filter_complex_threads','2'] + args)

def duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error',
        '-show_entries','format=duration','-of',
        'default=noprint_wrappers=1:nokey=1',str(path)]).strip())

def clean(value):
    return html.unescape(re.sub(r'<[^>]+>', '', str(value))).strip()

def display_text(value):
    value = str(value).translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','—':'-'}))
    return ' '.join(unicodedata.normalize('NFKD', value).encode('ascii','ignore').decode().split())

def keywords(item):
    content = (str(item.get('title',''))+' '+str(item.get('topic',''))).lower()
    queries = item.get('visual_keywords', [])
    if not isinstance(queries,list):
        queries = []
    queries = [q.strip()[:100] for q in queries if isinstance(q,str) and q.strip()]
    categories = [
        (r'\b(gta|gaming|game|games|rockstar|playstation|xbox)\b', ['gaming controller','video game','gaming','game console','gaming computer','game development','esports','joystick']),
        (r'\b(nvidia|gpu|semiconductor|graphics card)\b', ['graphics card','computer chip','semiconductor','data center','computer hardware']),
        (r'\b(storm|weather|hurricane|flood|rain)\b', ['storm clouds','heavy rain','thunderstorm','strong wind','rainfall']),
        (r'\b(restaurant|denny|pancakes?|mcdonald|food)\b', ['restaurant interior','pancakes','restaurant kitchen','breakfast']),
        (r'\b(ai|robot|chatgpt|artificial intelligence|machine learning)\b', ['artificial intelligence','robot technology','data center','computer chip','neural network']),
        (r'\b(inflation|prices|cost of living|groceries)\b', ['grocery shopping','supermarket shelves','shopping cart','grocery receipt','money counting']),
        (r'\b(electric car|electric vehicle|tesla|hybrid car)\b', ['electric car','car charging','car factory','electric battery']),
        (r'\b(economy|finance|stock market|banking)\b', ['stock market','financial chart','business meeting','money counting']),
        (r'\b(nba|basketball|wembanyama)\b', ['basketball','basketball player','basketball court']),
        (r'\b(nfl|american football)\b', ['american football','football helmet']),
        (r'\b(soccer|fifa|football)\b', ['soccer player','soccer stadium']),
        (r'\b(space|nasa|rocket|satellite)\b', ['rocket launch','space exploration','satellite','planet earth']),
        (r'\b(technology|innovation|invention)\b', ['computer technology','engineering laboratory','electronics'])]
    for pattern, extra in categories:
        if re.search(pattern,content):
            if pattern == r'\b(soccer|fifa|football)\b' and re.search(r'\b(nfl|american football)\b',content):
                continue
            queries.extend(extra)
    if not queries:
        queries.append(str(item.get('topic',''))[:100])
    return list(dict.fromkeys(q.lower().strip() for q in queries if q.strip()))[:32]

def relevant(tags, query):
    tags = str(tags).lower()
    ignored = {'the','and','with','for','news','today','global'}
    words = [w for w in re.findall(r'[a-z0-9]+',query.lower()) if len(w)>2 and w not in ignored]
    return bool(words) and all(re.search(r'\b'+re.escape(w)+r's?\b',tags) for w in words)

def download(url,path):
    with session.get(url,stream=True,timeout=45) as response:
        response.raise_for_status()
        size=0
        with open(path,'wb') as f:
            for chunk in response.iter_content(65536):
                if not chunk: continue
                size += len(chunk)
                if size > 45*1024*1024: raise ValueError('Media too large')
                f.write(chunk)

def valid_media(path):
    try:
        result=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(path)])
        streams=json.loads(result).get('streams',[])
        return bool(streams and streams[0].get('width',0)>=400 and streams[0].get('height',0)>=300)
    except Exception:
        return False

def search_pixabay(query,media):
    if not API_KEY: return []
    key=('pixabay',query,media)
    if key in cache: return cache[key]
    endpoint='https://pixabay.com/api/'+('videos/' if media=='video' else '')
    params={'key':API_KEY,'q':query,'per_page':30,'safesearch':'true','order':'popular'}
    if media=='image': params.update(image_type='photo',orientation='horizontal')
    try:
        response=session.get(endpoint,params=params,timeout=25)
        response.raise_for_status()
        cache[key]=response.json().get('hits',[])
        return cache[key]
    except Exception as error:
        print('Pixabay search failed:',type(error).__name__,flush=True)
        return []

def search_commons(query):
    key=('commons',query)
    if key in cache: return cache[key]
    params={'action':'query','generator':'search','gsrsearch':query+' filetype:bitmap','gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo','iiprop':'url|mime|size|extmetadata','iiurlwidth':1280,'format':'json'}
    results=[]
    try:
        response=session.get('https://commons.wikimedia.org/w/api.php',params=params,timeout=25)
        response.raise_for_status()
        for page in response.json().get('query',{}).get('pages',{}).values():
            infos=page.get('imageinfo',[])
            if not infos: continue
            info=infos[0]
            title=page.get('title','')
            if info.get('mime')!='image/jpeg' or re.search(r'diagram|schematic|circuit|document|logo|map|drawing',title,re.I) or not relevant(title,query): continue
            meta=info.get('extmetadata',{})
            def field(name): return clean(meta.get(name,{}).get('value',''))
            license_name,author,license_url=field('LicenseShortName'),field('Artist'),field('LicenseUrl')
            if license_name not in {'CC0','Public domain','CC BY 4.0','CC BY 3.0','CC BY 2.0'} or field('Restrictions'): continue
            if license_name.startswith('CC BY') and not (author and license_url): continue
            url=info.get('thumburl') or info.get('url')
            if url: results.append({'id':page.get('pageid'),'url':url,'page':info.get('descriptionurl',''),'title':title,'author':author,'license':license_name,'license_url':license_url,'provider':'Wikimedia Commons','query':query})
        cache[key]=results
    except Exception as error:
        print('Commons search failed:',type(error).__name__)
    return results

def get_media(item,folder,limit):
    files,sources=[],[]
    seen,hashes=set(),set()
    queries=keywords(item)
    print('Visual keywords:',queries,flush=True)
    def save(url,extension,source,identity):
        if identity in seen or len(files)>=limit: return False
        seen.add(identity)
        path=folder/f'media_{len(files)}{extension}'
        try:
            download(url,path)
            if not valid_media(path): raise ValueError('Invalid media')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes: raise ValueError('Duplicate media')
            hashes.add(digest)
            files.append(path); sources.append(source)
            return True
        except Exception:
            path.unlink(missing_ok=True)
            return False
    for media in ['video','image']:
        for query in queries:
            added=0
            for hit in search_pixabay(query,media):
                if len(files)>=limit: return files,sources
                tags=hit.get('tags','')
                if not relevant(tags,query) or re.search(r'\b(diagram|schematic|logo|document)\b',tags,re.I): continue
                if media=='video':
                    versions=hit.get('videos',{})
                    url=versions.get('medium',{}).get('url') or versions.get('small',{}).get('url')
                    extension='.mp4'
                else:
                    url=hit.get('largeImageURL'); extension='.jpg'
                if not url: continue
                source={'provider':'Pixabay','page':hit.get('pageURL',''),'author':hit.get('user',''),'license':'Pixabay Content License','license_url':'https://pixabay.com/service/license-summary/','query':query,'type':media}
                if save(url,extension,source,('pixabay',media,hit.get('id'))): added+=1
                if added>=2: break
    for query in queries:
        if len(files)>=limit: break
        for hit in search_commons(query):
            if save(hit['url'],'.jpg',hit,('commons',hit['id'])): break
    print('Media collected:',len(files),flush=True)
    return files,sources

def make_scene(source,target,seconds,width=WIDTH,height=HEIGHT,variant=0):
    frames=max(1,round(seconds*FPS))
    if source.suffix.lower()=='.jpg':
        zoom='min(zoom+0.0008,1.12)' if variant%2==0 else 'max(1.12-on*0.0008,1.0)'
        filters=(f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},'
                 f"zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={width}x{height}:fps={FPS},setsar=1")
        command=['-i',str(source)]
    else:
        filters=f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={FPS},setsar=1'
        start=0
        try: start=min(variant*1.5,max(0,duration(source)-seconds))
        except Exception: pass
        command=['-stream_loop','-1','-ss',str(start),'-i',str(source)]
    ffmpeg(command+['-vf',filters,'-frames:v',str(frames),'-an','-r',str(FPS),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','23','-pix_fmt','yuv420p',str(target)])

def find_subtitles(index,short=False):
    prefix='short' if short else 'video'
    for directory in ['audio','subtitles','captions']:
        path=Path(f'{directory}/{prefix}_{index}.srt')
        if path.exists() and path.stat().st_size: return path.resolve()
    return None

def make_thumbnail(index,item,media,folder):
    headline=display_text(item.get('thumbnail_text') or item.get('topic') or 'TRENDING NOW') or 'TRENDING NOW'
    headline=textwrap.fill(' '.join(headline.split()[:4]).upper(),width=17)
    text_file=folder/'thumbnail.txt'; text_file.write_text(headline,encoding='utf-8')
    filters=('scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,'
        'drawbox=x=0:y=430:w=iw:h=290:color=0x071329@0.78:t=fill,'
        'drawbox=x=0:y=430:w=iw:h=7:color=yellow:t=fill,'
        f"drawtext=fontfile={FONT}:text='TRENDPULSE GLOBAL':fontsize=30:fontcolor=white:box=1:boxcolor=0x071329@0.9:boxborderw=12:x=30:y=30,"
        f'drawtext=fontfile={FONT}:textfile={text_file}:expansion=none:fontsize=70:fontcolor=yellow:borderw=4:bordercolor=black:x=(w-tw)/2:y=440+(270-th)/2')
    target=output/f'thumbnail_{index}.jpg'
    for source in sorted(media,key=lambda p:p.suffix!='.jpg'):
        try:
            command=['-ss','0.5'] if source.suffix=='.mp4' else []
            ffmpeg(command+['-i',str(source),'-vf',filters,'-frames:v','1','-q:v','3',str(target)])
            if target.exists() and target.stat().st_size: return
        except Exception: target.unlink(missing_ok=True)
    raise RuntimeError('Thumbnail creation failed')

def save_credits(index,item,sources):
    credits=[]; seen=set()
    for source in sources:
        page=source.get('page','')
        identity=(page,source.get('author',''),source.get('query',''))
        if identity in seen: continue
        seen.add(identity)
        credits.append(f"{source.get('title',source.get('query','Media'))}\nAuthor: {source.get('author','')}\nSource: {page}\nLicense: {source.get('license','')}\n{source.get('license_url','')}\nChanges: cropped, resized, animated or text overlay.\n")
    credit_text='\n'.join(credits)
    music_license=Path('assets/background_license.txt')
    if Path('assets/background.mp3').exists() and music_license.exists() and music_license.stat().st_size:
        credit_text+='\nBackground music:\n'+music_license.read_text(encoding='utf-8')
    (output/f'credits_{index}.txt').write_text(credit_text,encoding='utf-8')
    (output/f'sources_{index}.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
    details=dict(item); details.update(media_credits=credit_text,review_required=True,version=VERSION)
    (output/f'details_{index}.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')

def render(index,item,media,audio,folder,short=False):
    width,height=(1080,1920) if short else (WIDTH,HEIGHT)
    prefix='short' if short else 'video'
    target=output/f'{prefix}_{index}.mp4'
    total=duration(audio)
    if total<=0: raise RuntimeError('Invalid audio')
    if short and total>180: raise RuntimeError('Short narration too long')
    scenes=[]; used=[]
    for n in range(math.ceil(total/SCENE_TIME)):
        seconds=min(SCENE_TIME,total-n*SCENE_TIME)
        if seconds<=0: break
        scene=folder/f'{prefix}_scene_{n}.mp4'
        created=False
        for offset in range(len(media)):
            position=(n+offset)%len(media)
            try:
                make_scene(media[position],scene,seconds,width,height,n//len(media))
                created=True
                if position not in used: used.append(position)
                break
            except subprocess.CalledProcessError: scene.unlink(missing_ok=True)
        if not created: raise RuntimeError('No valid scene')
        scenes.append(scene)
    concat=folder/f'{prefix}_concat.txt'
    concat.write_text('\n'.join(f"file '{p.as_posix()}'" for p in scenes),encoding='utf-8')
    combined=folder/f'{prefix}_combined.mp4'
    ffmpeg(['-f','concat','-safe','0','-i',str(concat),'-c','copy',str(combined)])
    hook=display_text((item.get('short_title') if short else item.get('opening_hook')) or item.get('title') or 'Trending Today')
    hook_file=folder/f'{prefix}_hook.txt'
    hook_file.write_text(textwrap.fill(' '.join(hook.split()[:16]),width=24 if short else 40),encoding='utf-8')
    font_size=54 if short else 56
    filters=('drawbox=x=0:y=0:w=iw:h=8:color=yellow:t=fill,'
        f"drawtext=fontfile={FONT}:text='TRENDPULSE GLOBAL':fontsize=30:fontcolor=white:box=1:boxcolor=0x071329@0.85:boxborderw=12:x=35:y=45,"
        f'drawtext=fontfile={FONT}:textfile={hook_file}:expansion=none:fontsize={font_size}:fontcolor=yellow:borderw=3:bordercolor=black:box=1:boxcolor=black@0.65:boxborderw=15:'
        "x=(w-tw)/2:y=(h-th)/2:enable='lt(t,5)',"
        f"drawtext=fontfile={FONT}:text='Illustrative footage':fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6:x=30:y=110")
    subtitles=find_subtitles(index,short)
    if subtitles:
        local_srt=folder/f'{prefix}_captions.srt'; local_srt.write_bytes(subtitles.read_bytes())
        margin=70 if short else 25
        filters+=f",subtitles={local_srt.as_posix()}:force_style='FontName=DejaVu Sans,FontSize=15,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV={margin}'"
    temporary=folder/f'{prefix}_final.mp4'
    command=['-stream_loop','-1','-i',str(combined),'-i',str(audio)]
    music=Path('assets/background.mp3'); music_license=Path('assets/background_license.txt')
    if music.exists() and music_license.exists() and music_license.stat().st_size:
        command+=['-stream_loop','-1','-i',str(music),'-filter_complex','[1:a]volume=1.0[voice];[2:a]volume=0.035[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]','-map','0:v:0','-map','[a]']
    else: command+=['-map','0:v:0','-map','1:a:0']
    ffmpeg(command+['-vf',filters,'-c:v','libx264','-preset','veryfast','-threads','2','-crf','22','-c:a','aac','-b:a','192k','-pix_fmt','yuv420p','-t',str(total),'-movflags','+faststart',str(temporary)])
    temporary.replace(target)
    print('SUCCESS:',target,flush=True)
    return used

def make_video(index,item):
    audio=Path(f'audio/video_{index}.mp3')
    if not audio.exists(): raise FileNotFoundError(audio)
    total=duration(audio)
    if total<180: print('WARNING: Video shorter than 3 minutes')
    print('Creating:',item.get('title',''),flush=True)
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        media,sources=get_media(item,folder,min(max(3,math.ceil(total/SCENE_TIME)),MAX_MEDIA))
        if len(media)<3: raise RuntimeError('Insufficient relevant media')
        used=render(index,item,media,audio,folder)
        make_thumbnail(index,item,[media[p] for p in used],folder)
        short_audio=Path(f'audio/short_{index}.mp3')
        if short_audio.exists():
            try: used=list(dict.fromkeys(used+render(index,item,media,short_audio,folder,short=True)))
            except Exception as error: print('Short skipped:',error)
        else: print('Short skipped: missing short audio',flush=True)
        save_credits(index,item,[sources[p] for p in used])
    return True

def main():
    with open('scripts.json',encoding='utf-8') as f:
        topics=json.load(f)['selected_topics']
    success=0
    for index,item in enumerate(topics,1):
        names=[f'video_{index}.mp4',f'short_{index}.mp4',f'thumbnail_{index}.jpg',f'credits_{index}.txt',f'sources_{index}.json',f'details_{index}.json']
        for name in names: (output/name).unlink(missing_ok=True)
        try:
            if make_video(index,item): success+=1
        except Exception as error:
            for name in names: (output/name).unlink(missing_ok=True)
            print(f'Video {index} failed: {type(error).__name__}: {error}',flush=True)
    print(f'TrendPulse AI V{VERSION}: {success}/{len(topics)} videos generated')
    if success==0: raise RuntimeError('No suitable videos generated')
    if success<len(topics): print('WARNING: Partial production; review before publishing',flush=True)

if __name__=='__main__':
    main()
