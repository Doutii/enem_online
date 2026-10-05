from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
import fitz
import os, re, json, uuid, zipfile
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, 'uploads')
GENERATED = os.path.join(BASE, 'generated')
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(GENERATED, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'enem-online-local-change-me'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
EXAMS = {}

LETTERS = ['A','B','C','D','E']

def clean_text(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s

def find_question_blocks(page):
    """Return question heading blocks with x/y coordinates, preserving two-column layout."""
    out=[]
    for b in page.get_text('blocks'):
        txt=b[4].strip()
        m=re.search(r'QUESTÃO\s+(\d{1,2})\b', txt.replace('\n',' ').strip())
        if m:
            y0=b[1] + (30 if not txt.replace('\n',' ').strip().startswith('QUESTÃO') else 0)
            out.append({'n':int(m.group(1)), 'x0':b[0], 'y0':y0, 'x1':b[2], 'y1':b[3]})
    return sorted(out, key=lambda z:(round(z['x0']/50), z['y0']))

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
    filename=f"q{block['n']:02d}_{page_idx+1}_{uuid.uuid4().hex[:8]}.png"
    path=os.path.join(out_dir, filename)
    pix.save(path)
    return filename

def parse_gabarito(path):
    doc=fitz.open(path)
    text='\n'.join(p.get_text() for p in doc)
    answers={}
    for n, ans in re.findall(r'(?m)^\s*(4[6-9]|[5-8]\d|90)\s+([A-E])\s*$', text):
        answers[int(n)]={'ingles':ans,'espanhol':ans}
    for n,a,b in re.findall(r'(?m)^\s*([1-5])\s+([A-E])\s+([A-E])\s*$', text):
        answers[int(n)]={'ingles':a,'espanhol':b}
    for n, ans in re.findall(r'(?m)^\s*((?:[6-9]|[1-3]\d|4[0-5]))\s+([A-E])\s*$', text):
        answers[int(n)]={'ingles':ans,'espanhol':ans}
    return answers

def parse_prova(path, gabarito_path, language='ingles'):
    doc=fitz.open(path)
    answers=parse_gabarito(gabarito_path)
    out_dir=os.path.join(GENERATED, uuid.uuid4().hex)
    os.makedirs(out_dir, exist_ok=True)
    questions=[]
    seen=set()
    for pi in range(len(doc)):
        page=doc[pi]
        for block in find_question_blocks(page):
            n=block['n']
            if 1 <= n <= 5:
                is_english = pi in (1,2) and not (pi==2 and block['x0']>doc[pi].rect.width/2)
                is_spanish = (pi in (2,3) and block['x0']>=doc[pi].rect.width/2) or (pi==3 and block['x0']<doc[pi].rect.width/2)
                if language=='ingles' and not ((n in (1,2,3) and pi==1) or (n in (4,5) and pi==2 and block['x0']<doc[pi].rect.width/2)):
                    continue
                if language=='espanhol' and not ((n==1 and pi==2 and block['x0']>doc[pi].rect.width/2) or (n in (2,3,4,5) and pi==3)):
                    continue
            if n in seen:
                continue
            if n not in answers:
                continue
            image=render_question_image(doc, pi, block, out_dir)
            questions.append({'numero':n,'imagem':image,'resposta':answers[n][language]})
            seen.add(n)
    questions.sort(key=lambda q:q['numero'])
    return questions, out_dir

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
    return render_template('index.html')

@app.route('/importar', methods=['POST'])
def importar():
    prova=request.files.get('prova')
    gabarito=request.files.get('gabarito')
    language=request.form.get('language','ingles')
    if not prova or not gabarito:
        flash('Selecione o PDF da prova e o PDF do gabarito.')
        return redirect(url_for('index'))
    sid=uuid.uuid4().hex
    ppath=os.path.join(UPLOADS, sid+'_prova.pdf')
    gpath=os.path.join(UPLOADS, sid+'_gabarito.pdf')
    prova.save(ppath); gabarito.save(gpath)
    try:
        questions, asset_dir=parse_prova(ppath,gpath,language)
    except Exception as e:
        flash('Não foi possível interpretar os PDFs: '+str(e))
        return redirect(url_for('index'))
    if len(questions) != 90:
        flash(f'Importação parcial: foram identificadas {len(questions)} questões. Verifique se o PDF é o Caderno Azul do 1º dia e o gabarito correspondente.')
    for q in questions: q['asset_dir']=asset_dir
    EXAMS[sid]={
        'prova':ppath,
        'gabarito':gpath,
        'language':language,
        'questions':questions,
        'asset_dir':asset_dir,
        'answers':{},
        'chutes':set()
    }
    session['exam_id']=sid
    return redirect(url_for('prova'))

@app.route('/prova')
def prova():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    return render_template(
        'prova.html',
        exam=exam,
        answers=exam.get('answers',{}),
        chutes=exam.get('chutes',set())
    )

@app.route('/responder', methods=['POST'])
def responder():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    answers=exam.get('answers',{})
    chutes=exam.get('chutes',set())

    for q in exam['questions']:
        number=str(q['numero'])
        v=request.form.get(f"q{number}")
        if v:
            answers[number]=v
        if request.form.get(f"chute_{number}") == '1':
            chutes.add(int(number))
        else:
            chutes.discard(int(number))

    exam['answers']=answers
    exam['chutes']=chutes

    if request.form.get('finalizar'):
        return redirect(url_for('resultado'))
    return redirect(url_for('prova'))

@app.route('/resultado')
def resultado():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))

    answers=exam.get('answers',{})
    chutes=exam.get('chutes',set())
    rows=[]
    wrong=[]
    correct=0
    chute_count=0
    chute_correct=0
    chute_wrong=0

    for q in exam['questions']:
        number=q['numero']
        user=answers.get(str(number))
        ok=user == q['resposta']
        is_chute=number in chutes

        if ok:
            correct+=1
        else:
            wrong.append(number)

        if is_chute:
            chute_count+=1
            if ok:
                chute_correct+=1
            else:
                chute_wrong+=1

        rows.append({
            'numero':number,
            'user':user or '—',
            'correct':q['resposta'],
            'ok':ok,
            'chute':is_chute
        })

    return render_template(
        'resultado.html',
        total=len(rows),
        correct=correct,
        wrong=len(rows)-correct,
        chute_count=chute_count,
        chute_correct=chute_correct,
        chute_wrong=chute_wrong,
        rows=rows,
        exam=exam
    )

@app.route('/baixar-erros')
def baixar_erros():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))

    answers=exam.get('answers',{})
    chutes=exam.get('chutes',set())

    # O PDF de estudo reúne toda questão errada + toda questão marcada como chute,
    # inclusive chutes que por acaso tenham sido acertados.
    selected=set()
    for q in exam['questions']:
        number=q['numero']
        if answers.get(str(number)) != q['resposta'] or number in chutes:
            selected.add(number)

    output=os.path.join(GENERATED, f"ENEM_questoes_revisao_{uuid.uuid4().hex[:8]}.pdf")
    make_wrong_pdf(exam['prova'], exam['questions'], selected, output)
    return send_file(output, as_attachment=True, download_name='ENEM_questoes_revisao.pdf')

@app.route('/static/question/<path:filename>')
def question_asset(filename):
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return '',404
    asset_dir=exam.get('asset_dir','')
    safe=os.path.basename(filename)
    return send_file(os.path.join(asset_dir,safe))

if __name__=='__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
