# ENEM Online

Aplicação web em **Python + Flask + PyMuPDF** para transformar provas oficiais do ENEM em simulados digitais.

O projeto foi pensado para estudo real e também como projeto de portfólio: importar uma prova e seu gabarito, responder no navegador, salvar o progresso, corrigir automaticamente e gerar uma revisão direcionada.

## ✨ Recursos

### Experiência de prova
- Mapa das 90 questões.
- Navegação por questão, com **Anterior / Próxima**.
- Indicadores de questão respondida, vazia e marcada como chute.
- Cronômetro de **5h30**.
- Autosave das respostas e chutes.
- Retomada após atualizar, fechar a página ou reiniciar o servidor.
- Layout responsivo para telas menores.
- Interface visual limpa, com foco no enunciado.

### Correção e revisão
- Correção automática pelo gabarito importado.
- Resultado geral.
- Desempenho separado por área.
- Estatísticas de chutes.
- PDF com questões erradas + questões marcadas como chute.
- Plano de estudo que prioriza erros e chutes por área.

### Biblioteca e persistência
- Provas importadas ficam salvas localmente.
- A mesma combinação de **prova + gabarito + idioma** é identificada por hash.
- Reimportar a mesma prova reutiliza os arquivos existentes e evita duplicação das imagens.
- Respostas, chutes, progresso e histórico ficam em `data/exams.json`.

### Histórico
- Registro das provas finalizadas.
- Média de desempenho.
- Melhor resultado.
- Quantidade de provas concluídas.
- Resultado individual de cada tentativa.

## 🧠 Análise de estudo e IA

A versão atual **não usa IA**.

O sistema já separa as questões que merecem revisão e informa a área correspondente. O próximo nível será mapear cada questão para competências, habilidades e conteúdos da matriz do ENEM e, posteriormente, usar IA para explicar os erros e montar um plano de estudo personalizado.

Isso mantém o projeto simples, barato e determinístico nesta etapa.

## 🧪 Testes

Os testes automatizados ficam em `tests/`.

Execute:

~~~bash
python -m unittest discover -s tests -p "test_*.py"
~~~

Eles verificam a lógica de correção, identificação de erros/chutes, separação por área e disponibilidade da rota inicial.

## 🚀 Instalação local

Recomendado: Python 3.10+.

~~~bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
~~~

Abra:

~~~text
http://127.0.0.1:5000
~~~

## 🌐 Preparação para publicação

O projeto já possui:
- `Procfile` para servidor WSGI;
- Gunicorn nas dependências;
- configuração por variáveis de ambiente;
- `SECRET_KEY` configurável;
- `HOST`, `PORT` e `FLASK_DEBUG` configuráveis;
- separação entre código e dados locais.

Para um deploy público de verdade, a próxima etapa deve trocar o catálogo JSON por um banco de dados persistente e mover os arquivos/imagens para armazenamento persistente. O armazenamento local de `uploads/`, `generated/` e `data/` é adequado para uso no computador, mas não deve ser tratado como armazenamento permanente em plataformas com filesystem efêmero.

## 📁 Estrutura

~~~text
enem_online/
├── app.py
├── requirements.txt
├── Procfile
├── .env.example
├── README.md
├── tests/
├── templates/
│   ├── index.html
│   ├── prova.html
│   ├── resultado.html
│   ├── historico.html
│   └── estudo.html
├── static/
│   ├── style.css
│   └── app.js
├── uploads/
├── generated/
└── data/
    └── exams.json
~~~

## 🔐 Dados

`uploads/`, `generated/` e `data/` são ignorados pelo Git.

Isso evita enviar para o repositório:
- PDFs importados;
- imagens geradas das questões;
- PDFs de revisão;
- respostas e histórico pessoais.

## 📌 Próximos passos

1. Suporte organizado a diferentes anos, dias e cadernos.
2. Melhor identificação automática de ano/caderno no título da prova.
3. Banco de dados para publicação.
4. Mapeamento das questões para competências, habilidades e conteúdos.
5. Análise pedagógica dos erros.
6. IA opcional para explicar erros e montar estudos personalizados.
