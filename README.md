# ENEM Online

Aplicação local em Python/Flask para transformar provas do ENEM em uma experiência digital: importar prova + gabarito, responder no navegador, corrigir automaticamente e gerar um PDF de revisão.

## Recursos atuais

- Navegação por mapa das 90 questões.
- Questão individual com anterior/próxima.
- Marcação de chute.
- Cronômetro de 5h30.
- Salvamento automático de respostas e chutes.
- Retomada após fechar/reabrir a página ou reiniciar o servidor.
- Biblioteca local de provas já importadas.
- Deduplicação por hash: a mesma prova + gabarito + idioma reutiliza os PDFs e as imagens já gerados.
- Resultado com desempenho geral e por área.
- PDF com questões erradas + questões marcadas como chute.
- Questões 1–5 com escolha entre Inglês e Espanhol.

## Requisitos

- Python 3.10+

## Instalação

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000

## Dados locais

As provas importadas, imagens processadas e respostas ficam apenas no computador:

- `uploads/` — PDFs originais importados.
- `generated/` — imagens das questões e PDFs gerados.
- `data/exams.json` — catálogo, respostas, chutes e progresso.

Essas pastas são ignoradas pelo Git para não enviar arquivos pessoais ou grandes para o GitHub.

## Próximas melhorias

- suporte a outros anos e cadernos;
- histórico de desempenho;
- PDF de revisão mais completo;
- estatísticas de evolução;
- testes automatizados;
- análise de desempenho para estudo.
