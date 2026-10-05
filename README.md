# ENEM Online — V1

Aplicação local em Python/Flask para importar prova + gabarito em PDF, fazer a prova no navegador, corrigir e gerar PDF somente das questões erradas.

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

## V1
O parser foi construído para o layout do ENEM 2024, 1º dia, Caderno 1 Azul. Ele preserva questões com gráficos/imagens como recortes do PDF original. As questões 1–5 permitem escolher Inglês ou Espanhol, de acordo com o gabarito.

## Próximas melhorias
- cronômetro de 5h30;
- grade de navegação 1–90;
- salvar/reabrir provas;
- suporte aos demais cadernos e anos;
- PDF de erros com layout ainda mais refinado;
- estatísticas por área e histórico de desempenho.
