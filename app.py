from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify
import fitz
import os, re, json, uuid, time, hashlib, unicodedata
from threading import Lock
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, 'uploads')
GENERATED = os.path.join(BASE, 'generated')
DATA = os.path.join(BASE, 'data')
CATALOG = os.path.join(DATA, 'exams.json')
DURATION_SECONDS = 5 * 60 * 60 + 30 * 60
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(GENERATED, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'enem-online-local-change-me')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
EXAMS = {}
CATALOG_LOCK = Lock()

def file_sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def save_catalog():
    data={}
    for sid,e in EXAMS.items():
        data[sid]={k:v for k,v in e.items() if k!='chutes'}
        data[sid]['chutes']=sorted(e.get('chutes',set()))
    os.makedirs(DATA, exist_ok=True)
    with CATALOG_LOCK:
        tmp=f"{CATALOG}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp,'w',encoding='utf-8') as f:
                json.dump(data,f,ensure_ascii=False,indent=2)
                f.flush()
                os.fsync(f.fileno())
            for _ in range(5):
                try:
                    os.replace(tmp,CATALOG)
                    break
                except PermissionError:
                    time.sleep(0.15)
            else:
                raise PermissionError(f"Não foi possível substituir {CATALOG}; o arquivo pode estar em uso.")
        finally:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except OSError: pass

def load_exams():
    if not os.path.exists(CATALOG): return
    try:
        with open(CATALOG,encoding='utf-8') as f: data=json.load(f)
    except (OSError,json.JSONDecodeError): return
    for sid,e in data.items():
        e.setdefault('exam_type','humanas')
        if os.path.exists(e.get('prova','')) and os.path.exists(e.get('gabarito','')) and os.path.isdir(e.get('asset_dir','')):
            e['chutes']=set(e.get('chutes',[])); e.setdefault('answers',{}); e.setdefault('current_question',0); e.setdefault('started_at',None); e.setdefault('paused',False); e.setdefault('paused_remaining',DURATION_SECONDS); e.setdefault('completed',False); e.setdefault('updated_at',0); e.setdefault('history',[]); EXAMS[sid]=e


def timestamp_br(value):
    if not value: return '—'
    return time.strftime('%d/%m/%Y %H:%M', time.localtime(float(value)))
app.jinja_env.filters['timestamp_br']=timestamp_br

def identify_exam_cover(path):
    """Tenta identificar ano, dia, caderno e cor pela capa/texto inicial do PDF."""
    doc=fitz.open(path)
    first_text='\n'.join(doc[i].get_text() for i in range(min(3,len(doc))))
    doc.close()
    normalized=_norm_word(first_text)
    year_match=re.search(r'\b(20(?:0\d|1\d|2\d))\b',normalized)
    year=year_match.group(1) if year_match else None

    day=None
    if re.search(r'\b2\s*(?:O|º|°)?\s*DIA\b|SEGUNDO\s+DIA',normalized):
        day=2
    elif re.search(r'\b1\s*(?:O|º|°)?\s*DIA\b|PRIMEIRO\s+DIA',normalized):
        day=1

    booklet_match=re.search(r'\bCADERNO\s*(?:DE\s*)?(\d{1,2})\b',normalized)
    booklet=booklet_match.group(1) if booklet_match else None
    colors=('AZUL','AMARELO','BRANCO','ROSA','VERDE','CINZA','LARANJA')
    color=next((c.title() for c in colors if re.search(r'\b'+c+r'\b',normalized)),None)

    exam_type='exatas' if day==2 else 'humanas' if day==1 else None
    parts=[]
    if year: parts.append('ENEM '+year)
    if day: parts.append(f'{day}º Dia')
    if booklet: parts.append('Caderno '+booklet)
    if color: parts.append(color)
    title=' — '.join(parts) if parts else None
    return {'year':year,'day':day,'booklet':booklet,'color':color,'exam_type':exam_type,'title':title,'detected':bool(year or day or booklet or color)}

def area_for_question(exam, numero):
    n=int(numero)
    if exam.get('exam_type','humanas') == 'exatas':
        return 'Ciências da Natureza' if 91 <= n <= 135 else 'Matemática'
    return 'Linguagens' if n <= 45 else 'Ciências Humanas'

def build_result(exam):
    answers=exam.get('answers',{})
    chutes=exam.get('chutes',set())
    rows=[]
    for q in exam['questions']:
        n=q['numero']
        user=answers.get(str(n))
        ok=q.get('resposta') is not None and user==q['resposta']
        rows.append({'numero':n,'user':user or '—','correct':q.get('resposta') or '—','ok':ok,'chute':n in chutes,'area':area_for_question(exam,n)})
    return rows

def record_history(exam):
    rows=build_result(exam)
    correct=sum(r['ok'] for r in rows)
    chutes=sum(r['chute'] for r in rows)
    record={
        'timestamp':time.time(),
        'correct':correct,
        'wrong':len(rows)-correct,
        'total':len(rows),
        'percent':round(correct*100/len(rows),1) if rows else 0,
        'chutes':chutes,
        'areas':{
            area: {
                'correct':sum(r['ok'] for r in rows if r['area']==area),
                'total':sum(1 for r in rows if r['area']==area)
            }
            for area in dict.fromkeys(r['area'] for r in rows)
        }
    }
    exam.setdefault('history',[]).append(record)
    return record

def study_summary(exam):
    rows=build_result(exam)
    grouped={}
    for r in rows:
        if not r['ok'] or r['chute']:
            area=r['area']
            grouped.setdefault(area,{'wrong':0,'chutes':0,'questions':[]})
            if not r['ok']: grouped[area]['wrong']+=1
            if r['chute']: grouped[area]['chutes']+=1
            grouped[area]['questions'].append(r['numero'])
    return grouped

def remaining_seconds(exam):
    if exam.get('paused'):
        return max(0,int(exam.get('paused_remaining',DURATION_SECONDS)))
    if not exam.get('started_at'): return DURATION_SECONDS
    return max(0,DURATION_SECONDS-int(time.time()-float(exam['started_at'])))

load_exams()

LETTERS = ['A','B','C','D','E']

def clean_text(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s

def _norm_word(value):
    value=unicodedata.normalize('NFKD', value or '')
    return ''.join(ch for ch in value if not unicodedata.combining(ch)).upper()

def find_question_blocks(page):
    """Localiza QUESTÃO + número usando as palavras do PDF, sem depender de blocos."""
    words=page.get_text('words', sort=True)
    out=[]
    for i,w in enumerate(words):
        word=_norm_word(w[4])
        if word not in ('QUESTAO','QUESTAO.'):
            continue
        if i+1 >= len(words):
            continue
        nxt=words[i+1]
        raw=re.sub(r'[^0-9]','',nxt[4])
        if not raw:
            continue
        n=int(raw)
        if not 1 <= n <= 180:
            continue
        out.append({'n':n,'x0':w[0],'y0':w[1],'x1':nxt[2],'y1':max(w[3],nxt[3])})

    # Fallback para PDFs cuja extração não separa as palavras como esperado.
    if not out:
        for b in page.get_text('blocks', sort=True):
            txt=b[4].replace('\\n',' ')
            m=re.search(r'QUEST[AÃ]O\\s+(\\d{1,3})\\b',txt,re.I)
            if m:
                out.append({'n':int(m.group(1)),'x0':b[0],'y0':b[1],'x1':b[2],'y1':b[3]})

    # Remove apenas duplicatas da mesma posição.
    unique=[]
    seen=set()
    for item in sorted(out,key=lambda z:(z['y0'],z['x0'])):
        key=(item['n'],round(item['x0'],1),round(item['y0'],1))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def column_bounds(page, x0):
    w=page.rect.width
    mid=w/2
    if x0 < mid:
        return 18, mid-7
    return mid+2, w-18

def render_question_image(doc, page_idx, block, out_dir):
    page=doc[page_idx]
    left,right=column_bounds(page, block['x0'])
    same_left = block['x0'] < page.rect.width/2
    candidates=[b for b in find_question_blocks(page) if (b['x0'] < page.rect.width/2) == same_left and b['y0'] > block['y0']+2]
    if candidates:
        bottom=min(candidates, key=lambda b:b['y0'])['y0']-10
    else:
        bottom=page.rect.height-42
    top=max(0, block['y0']-8)
    rect=fitz.Rect(left, top, right, bottom)
    pix=page.get_pixmap(matrix=fitz.Matrix(1.6,1.6), clip=rect, alpha=False)
    filename=f"q{block['n']:02d}_{page_idx+1}.png"
    path=os.path.join(out_dir, filename)
    pix.save(path)
    return filename

def parse_gabarito(path):
    doc=fitz.open(path)
    text='\n'.join(p.get_text() for p in doc)
    doc.close()
    answers={}

    # 1º dia: questões 6–90 possuem uma única resposta.
    for n,ans in re.findall(r'(?m)^\s*(6|[7-9]|[1-8]\d|90)\s+([A-E])\s*$',text):
        answers[int(n)]={'ingles':ans,'espanhol':ans,'anulada':False}

    # 2º dia: questões 91–180 possuem uma única resposta.
    for n,ans in re.findall(r'(?m)^\s*(9[1-9]|1[0-7]\d|180)\s+([A-E])\s*$',text):
        answers[int(n)]={'ingles':ans,'espanhol':ans,'anulada':False}

    # Fallback para tabelas cuja extração muda espaços/quebras de linha.
    normalized=re.sub(r'\s+',' ',text)
    for n,ans in re.findall(r'(?<!\d)(9[1-9]|1[0-7]\d|180)\s+([A-E])(?![A-Z])',normalized):
        answers[int(n)]={'ingles':ans,'espanhol':ans,'anulada':False}

    # Questões anuladas não recebem letra.
    for n in re.findall(r'(?i)(?<!\d)(9[1-9]|1[0-7]\d|180)\s+Anulado',normalized):
        answers[int(n)]={'ingles':None,'espanhol':None,'anulada':True}

    # 1º dia: questões 1–5 possuem duas colunas de idioma.
    for n,a,b in re.findall(r'(?m)^\s*([1-5])\s+([A-E])\s+([A-E])\s*$',text):
        answers[int(n)]={'ingles':a,'espanhol':b,'anulada':False}

    return answers


def parse_prova(path, gabarito_path, language='ingles', exam_type='humanas', out_dir=None):
    doc=fitz.open(path)
    answers=parse_gabarito(gabarito_path)
    if out_dir is None:
        out_dir=os.path.join(GENERATED,uuid.uuid4().hex)
    os.makedirs(out_dir,exist_ok=True)

    questions=[]
    seen=set()
    expected_start=1 if exam_type=='humanas' else 91
    expected_end=90 if exam_type=='humanas' else 180

    for pi in range(len(doc)):
        page=doc[pi]
        for block in find_question_blocks(page):
            n=block['n']
            if not expected_start <= n <= expected_end or n in seen:
                continue

            # No 1º dia, seleciona apenas uma versão das questões de idioma 1–5.
            if exam_type=='humanas' and 1 <= n <= 5:
                if language=='ingles':
                    valid=((n in (1,2,3) and pi==1) or
                           (n in (4,5) and pi==2 and block['x0'] < page.rect.width/2))
                else:
                    valid=((n==1 and pi==2 and block['x0'] > page.rect.width/2) or
                           (n in (2,3,4,5) and pi==3))
                if not valid:
                    continue

            image=render_question_image(doc,pi,block,out_dir)
            answer_data=answers.get(n,{})
            questions.append({
                'numero':n,
                'imagem':image,
                'resposta':answer_data.get(language),
                'anulada':bool(answer_data.get('anulada',False))
            })
            seen.add(n)

    doc.close()
    questions.sort(key=lambda q:q['numero'])
    return questions,out_dir


def make_wrong_pdf(prova_path, question_records, selected_numbers, output_path):
    out=fitz.open()
    for q in question_records:
        if q['numero'] not in selected_numbers:
            continue
        img_path=os.path.join(q['asset_dir'], q['imagem'])
        page=out.new_page(width=595, height=842)
        page.insert_text((40,45), f"ENEM — Questão {q['numero']}", fontsize=14)
        page.insert_image(fitz.Rect(35,60,560,810), filename=img_path, keep_proportion=True)
    out.save(output_path)
    out.close()

@app.route('/')
def index():
    cards=[{'id':sid,'title':e.get('title','ENEM — Caderno Azul'),'answered':len(e.get('answers',{})),'total':len(e.get('questions',[])),'completed':e.get('completed',False),'paused':e.get('paused',False),'updated_at':e.get('updated_at',0)} for sid,e in EXAMS.items()]
    cards.sort(key=lambda x:x['updated_at'],reverse=True)
    return render_template('index.html',saved_exams=cards)

@app.route('/importar',methods=['POST'])
def importar():
    prova=request.files.get('prova')
    gabarito=request.files.get('gabarito')
    exam_type=request.form.get('exam_type','humanas')
    language=request.form.get('language','ingles')

    if not prova or not gabarito or not prova.filename or not gabarito.filename:
        flash('Selecione o PDF da prova e o PDF do gabarito.')
        return redirect(url_for('index'))

    if exam_type not in ('humanas','exatas'):
        flash('Tipo de prova inválido.')
        return redirect(url_for('index'))

    # 1. Salva cada upload em temporário único. Nada é criado na pasta final ainda.
    token=uuid.uuid4().hex
    staging=os.path.join(UPLOADS,'.staging')
    os.makedirs(staging,exist_ok=True)
    ptmp=os.path.join(staging,f'{token}_prova.pdf')
    gtmp=os.path.join(staging,f'{token}_gabarito.pdf')
    prova.save(ptmp)
    gabarito.save(gtmp)

    try:
        if os.path.getsize(ptmp)==0 or os.path.getsize(gtmp)==0:
            raise ValueError('um dos arquivos enviados está vazio')

        # 2. Abre os dois PDFs antes de alterar qualquer arquivo definitivo.
        test=fitz.open(ptmp)
        if test.page_count==0:
            test.close()
            raise ValueError('a prova não possui páginas')
        test.close()
        test=fitz.open(gtmp)
        if test.page_count==0:
            test.close()
            raise ValueError('o gabarito não possui páginas')
        test.close()

        cover=identify_exam_cover(ptmp)
        if cover.get('exam_type'):
            exam_type=cover['exam_type']
        if exam_type=='humanas' and language not in ('ingles','espanhol'):
            language='ingles'

        ph=file_sha256(ptmp)
        gh=file_sha256(gtmp)
        sid=hashlib.sha256(f'{ph}:{gh}:{exam_type}:{language}'.encode()).hexdigest()[:24]

        type_dir='humanas' if exam_type=='humanas' else 'exatas'
        upload_dir=os.path.join(UPLOADS,type_dir)
        final_assets=os.path.join(GENERATED,type_dir,sid)
        os.makedirs(upload_dir,exist_ok=True)

        ppath=os.path.join(upload_dir,f'{sid}_prova.pdf')
        gpath=os.path.join(upload_dir,f'{sid}_gabarito.pdf')

        # 3. Se a prova já foi importada e os arquivos/imagens continuam válidos,
        # reutiliza tudo. Nenhuma imagem é recriada.
        existing=EXAMS.get(sid)
        if existing and os.path.isfile(ppath) and os.path.isfile(gpath) and os.path.isdir(final_assets):
            session['exam_id']=sid
            flash('Esta prova já está salva. Abrindo a prova existente sem duplicar arquivos.')
            return redirect(url_for('prova'))

        # 4. Gera imagens em staging. Só publica depois de encontrar exatamente 90.
        image_stage=os.path.join(GENERATED,'.staging',sid)
        if os.path.isdir(image_stage):
            import shutil
            shutil.rmtree(image_stage)
        os.makedirs(image_stage,exist_ok=True)

        questions,_=parse_prova(ptmp,gtmp,language,exam_type,image_stage)

        expected_start=1 if exam_type=='humanas' else 91
        expected_end=90 if exam_type=='humanas' else 180
        expected=set(range(expected_start,expected_end+1))
        found={q['numero'] for q in questions}
        missing=sorted(expected-found)

        if len(questions)!=90 or missing:
            import shutil
            shutil.rmtree(image_stage,ignore_errors=True)
            raise ValueError(
                f'foram encontradas {len(questions)}/90 questões. '
                f'Faltando: {", ".join(map(str,missing[:15]))}'
            )

        # 5. Publica os PDFs definitivos somente após a prova inteira ter sido lida.
        # É um único arquivo final por prova, identificado pelo hash.
        os.replace(ptmp,ppath)
        os.replace(gtmp,gpath)

        import shutil
        if os.path.isdir(final_assets):
            shutil.rmtree(final_assets)
        os.makedirs(os.path.dirname(final_assets),exist_ok=True)
        os.replace(image_stage,final_assets)

        for q in questions:
            q['asset_dir']=final_assets

        # Remove somente artefatos legados da mesma prova que ficaram na
        # estrutura antiga. Não toca em outras provas.
        legacy_prova=os.path.join(UPLOADS,f'{sid}_prova.pdf')
        legacy_gabarito=os.path.join(UPLOADS,f'{sid}_gabarito.pdf')
        legacy_assets=os.path.join(GENERATED,sid)
        for legacy_path in (legacy_prova,legacy_gabarito):
            try:
                if os.path.abspath(legacy_path) != os.path.abspath(ppath) and os.path.isfile(legacy_path):
                    os.remove(legacy_path)
            except OSError:
                pass
        if os.path.abspath(legacy_assets) != os.path.abspath(final_assets) and os.path.isdir(legacy_assets):
            shutil.rmtree(legacy_assets,ignore_errors=True)

        EXAMS[sid]={
            'prova':ppath,
            'gabarito':gpath,
            'language':language,
            'exam_type':exam_type,
            'title':(cover.get('title') if cover.get('title') and cover.get('day') else ((cover.get('title') + ' — ' if cover.get('title') else 'ENEM — ') + ('1º Dia' if exam_type=='humanas' else '2º Dia') + (' — Caderno Azul' if not cover.get('booklet') else ''))),
            'questions':questions,
            'asset_dir':final_assets,
            'answers':{},
            'chutes':set(),
            'current_question':0,
            'started_at':time.time(),
            'paused':False,
            'paused_remaining':DURATION_SECONDS,
            'completed':False,
            'updated_at':time.time(),
            'history':[]
        }
        save_catalog()
        session['exam_id']=sid
        flash("Prova identificada: {}. Importação concluída com 90 questões.".format(EXAMS[sid]['title']))
        return redirect(url_for('prova'))

    except Exception as e:
        # Nunca deixa temporários ou uma prova parcialmente importada.
        for temp_path in (ptmp,gtmp):
            try: os.remove(temp_path)
            except OSError: pass
        flash('Não foi possível importar os PDFs: '+str(e))
        return redirect(url_for('index'))


@app.route('/excluir/<sid>',methods=['POST'])
def excluir(sid):
    exam=EXAMS.get(sid)
    if not exam:
        flash('Esta prova já não está na lista.')
        return redirect(url_for('index'))

    # Apaga primeiro do catálogo ativo e persiste; depois remove somente os
    # arquivos pertencentes a esta prova.
    EXAMS.pop(sid,None)
    if session.get('exam_id')==sid:
        session.pop('exam_id',None)
    save_catalog()

    import shutil
    for key in ('prova','gabarito'):
        path=exam.get(key)
        if path and os.path.isfile(path):
            try: os.remove(path)
            except OSError: pass
    asset_dir=exam.get('asset_dir')
    if asset_dir and os.path.isdir(asset_dir):
        try: shutil.rmtree(asset_dir)
        except OSError: pass
    flash('Prova excluída.')
    return redirect(url_for('index'))


@app.route('/refazer/<sid>', methods=['POST'])
def refazer(sid):
    exam=EXAMS.get(sid)
    if not exam: return redirect(url_for('index'))
    exam['answers']={}
    exam['chutes']=set()
    exam['current_question']=0
    exam['started_at']=time.time()
    exam['paused']=False
    exam['paused_remaining']=DURATION_SECONDS
    exam['completed']=False
    exam['updated_at']=time.time()
    save_catalog()
    session['exam_id']=sid
    return redirect(url_for('prova'))

@app.route('/abrir/<sid>')
def abrir(sid):
    if sid not in EXAMS: return redirect(url_for('index'))
    session['exam_id']=sid
    return redirect(url_for('resultado') if EXAMS[sid].get('completed') else url_for('prova'))

@app.route('/prova')
def prova():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    if exam.get('completed'): return redirect(url_for('resultado'))
    if not exam.get('started_at') and not exam.get('paused'): exam['started_at']=time.time(); save_catalog()
    return render_template('prova.html',exam=exam,answers=exam.get('answers',{}),chutes=exam.get('chutes',set()),remaining=remaining_seconds(exam),current_question=exam.get('current_question',0),paused=exam.get('paused',False))

@app.route('/pausar',methods=['POST'])
def pausar():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    if exam.get('completed'): return redirect(url_for('resultado'))
    exam['paused_remaining']=remaining_seconds(exam)
    exam['paused']=True
    exam['started_at']=None
    exam['updated_at']=time.time()
    save_catalog()
    return redirect(url_for('index'))

@app.route('/salvar',methods=['POST'])
def salvar():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return jsonify({'ok':False}),404
    data=request.get_json(silent=True) or {}
    exam['answers']={str(k):v for k,v in data.get('answers',{}).items() if v in LETTERS}
    exam['chutes']=set(int(x) for x in data.get('chutes',[]))
    exam['current_question']=max(0,min(len(exam['questions'])-1,int(data.get('current_question',0))))
    exam['updated_at']=time.time(); save_catalog()
    return jsonify({'ok':True,'remaining':remaining_seconds(exam)})

@app.route('/responder',methods=['POST'])
def responder():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    answers=exam.get('answers',{}); chutes=exam.get('chutes',set())
    for q in exam['questions']:
        n=str(q['numero']); v=request.form.get('q'+n)
        if v: answers[n]=v
        if request.form.get('chute_'+n)=='1': chutes.add(int(n))
        else: chutes.discard(int(n))
    exam['answers']=answers; exam['chutes']=chutes; exam['updated_at']=time.time()
    should_finish=bool(request.form.get('finalizar') or remaining_seconds(exam)<=0)
    if should_finish and not exam.get('completed'):
        exam['completed']=True
        record_history(exam)
    save_catalog()
    return redirect(url_for('resultado' if exam.get('completed') else 'prova'))

@app.route('/resultado')
def resultado():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    rows=build_result(exam)
    correct=sum(r['ok'] for r in rows)
    chutes=[r for r in rows if r['chute']]
    area_stats=[]
    seen_areas=[]
    for r in rows:
        if r['area'] in seen_areas:
            continue
        seen_areas.append(r['area'])
        sub=[x for x in rows if x['area']==r['area']]
        ac=sum(x['ok'] for x in sub)
        area_stats.append({'name':r['area'],'correct':ac,'total':len(sub),'percent':ac*100/len(sub) if sub else 0})
    return render_template('resultado.html',total=len(rows),correct=correct,wrong=len(rows)-correct,
                           chute_count=len(chutes),chute_correct=sum(r['ok'] for r in chutes),
                           chute_wrong=sum(not r['ok'] for r in chutes),rows=rows,exam=exam,
                           area_stats=area_stats,history=exam.get('history',[]))

@app.route('/historico')
def historico():
    entries=[]
    for sid,exam in EXAMS.items():
        for h in exam.get('history',[]):
            item=dict(h); item['exam_id']=sid; item['title']=exam.get('title','ENEM'); entries.append(item)
    entries.sort(key=lambda x:x.get('timestamp',0),reverse=True)
    avg=sum(x['percent'] for x in entries)/len(entries) if entries else 0
    best=max((x['percent'] for x in entries),default=0)
    return render_template('historico.html',entries=entries,total_attempts=len(entries),avg=avg,best=best)

@app.route('/estudo')
def estudo():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    return render_template('estudo.html',exam=exam,summary=study_summary(exam),focus=[r for r in build_result(exam) if not r['ok'] or r['chute']])

@app.route('/baixar-erros')
def baixar_erros():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    answers=exam.get('answers',{}); chutes=exam.get('chutes',set())
    selected={q['numero'] for q in exam['questions'] if answers.get(str(q['numero']))!=q['resposta'] or q['numero'] in chutes}
    output=os.path.join(GENERATED,f"ENEM_questoes_revisao_{uuid.uuid4().hex[:8]}.pdf")
    make_wrong_pdf(exam['prova'],exam['questions'],selected,output)
    return send_file(output,as_attachment=True,download_name='ENEM_questoes_revisao.pdf')

@app.route('/static/question/<path:filename>')
def question_asset(filename):
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return '',404
    safe=os.path.basename(filename); path=os.path.join(exam.get('asset_dir',''),safe)
    return send_file(path) if os.path.isfile(path) else ('',404)

if __name__=='__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG','0')=='1', host=os.environ.get('HOST','127.0.0.1'), port=int(os.environ.get('PORT','5000')))