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
    # Find next question in same column. Otherwise use near page bottom.
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
    # 46-90 straightforward
    for n, ans in re.findall(r'(?m)^\s*(4[6-9]|[5-8]\d|90)\s+([A-E])\s*$', text):
        answers[int(n)]={'ingles':ans,'espanhol':ans}
    # 1-5 line has two columns: 1 C C ...
    for n,a,b in re.findall(r'(?m)^\s*([1-5])\s+([A-E])\s+([A-E])\s*$', text):
        answers[int(n)]={'ingles':a,'espanhol':b}
    # 6-45 single column
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
            # Skip the alternate language version that is not selected.
            if 1 <= n <= 5:
                # Page 2-3 = English, page 3-4 = Spanish. Detect by x position and page.
                is_english = pi in (1,2) and not (pi==2 and block['x0']>doc[pi].rect.width/2)
                is_spanish = (pi in (2,3) and block['x0']>=doc[pi].rect.width/2) or (pi==3 and block['x0']<doc[pi].rect.width/2)
                # More reliable mapping for this official layout: English Q1-3 p2, Q4-5 p3 left; Spanish Q1 p3 right, Q2-5 p4.
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
    # Validate expected 90 objective questions (language choice still counts once for 1-5).
    return questions, out_dir

def make_wrong_pdf(prova_path, question_records, wrong_numbers, output_path):
    src=fitz.open(prova_path)
    out=fitz.open()
    # Recreate a clean study PDF from the rendered snippets. This avoids carrying unrelated questions.
    for q in question_records:
        if q['numero'] not in wrong_numbers:
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
    EXAMS[sid]={'prova':ppath,'gabarito':gpath,'language':language,'questions':questions,'asset_dir':asset_dir,'answers':{}}
    session['exam_id']=sid
    return redirect(url_for('prova'))

@app.route('/prova')
def prova():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    return render_template('prova.html', exam=exam, answers=exam.get('answers',{}))

@app.route('/responder', methods=['POST'])
def responder():
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return redirect(url_for('index'))
    answers=exam.get('answers',{})
    for q in exam['questions']:
        v=request.form.get(f"q{q['numero']}")
        if v: answers[str(q['numero'])]=v
    exam['answers']=answers
    if request.form.get('finalizar'):
        return redirect(url_for('resultado'))
    return redirect(url_for('prova'))

@app.route('/resultado')
def resultado():
    exam=EXAMS.get(session.get('exam_id')); answers=(exam or {}).get('answers',{})
    if not exam: return redirect(url_for('index'))
    rows=[]; wrong=[]; correct=0
    for q in exam['questions']:
        user=answers.get(str(q['numero']))
        ok=user == q['resposta']
        if ok: correct+=1
        else: wrong.append(q['numero'])
        rows.append({'numero':q['numero'],'user':user or '—','correct':q['resposta'],'ok':ok})
    return render_template('resultado.html', total=len(rows), correct=correct, wrong=len(rows)-correct, rows=rows, exam=exam)

@app.route('/baixar-erros')
def baixar_erros():
    exam=EXAMS.get(session.get('exam_id')); answers=(exam or {}).get('answers',{})
    if not exam: return redirect(url_for('index'))
    wrong=[]
    for q in exam['questions']:
        if answers.get(str(q['numero'])) != q['resposta']:
            wrong.append(q['numero'])
    output=os.path.join(GENERATED, f"ENEM_questoes_erradas_{uuid.uuid4().hex[:8]}.pdf")
    make_wrong_pdf(exam['prova'], exam['questions'], wrong, output)
    return send_file(output, as_attachment=True, download_name='ENEM_questoes_erradas.pdf')

@app.route('/static/question/<path:filename>')
def question_asset(filename):
    exam=EXAMS.get(session.get('exam_id'))
    if not exam: return '',404
    asset_dir=exam.get('asset_dir','')
    safe=os.path.basename(filename)
    return send_file(os.path.join(asset_dir,safe))

if __name__=='__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
