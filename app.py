import dash
from dash import dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc
import base64
import io
import os
import fitz  # PyMuPDF
from textblob import TextBlob
from wordcloud import WordCloud
import plotly.graph_objects as go
import plotly.io as pio
from PIL import Image as PILImage
import pandas as pd
import csv

# Configuração inicial
os.makedirs("relatorios", exist_ok=True)

PALAVRAS_CHAVE = [
    "inflação", "selic", "pib", "atividade", "juros", "expectativas",
    "economia", "mercado", "política", "monetária", "taxa", "crédito",
    "produção", "consumo", "demanda", "oferta", "preços", "riscos"
]

STOPWORDS = ["da", "de", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos",
             "um", "uma", "os", "as", "ao", "aos", "que", "com", "por", "para",
             "a", "o", "como", "mais", "mas", "se", "sem", "são", "esta", "este"]

TRADUCOES = {
    'inflação': 'inflation', 'juros': 'interest', 'selic': 'interest rate',
    'pib': 'gdp', 'atividade': 'activity', 'expectativas': 'expectations',
    'economia': 'economy', 'mercado': 'market', 'política': 'policy',
    'monetária': 'monetary'
}

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Análise COPOM"

app.layout = dbc.Container([
    html.H2("Analisador de Atas do COPOM", className="text-center my-3"),

    dcc.Upload(id='upload-pdf', children=html.Div(['Arraste ou selecione o PDF']),
               style={'width': '100%', 'height': '60px', 'lineHeight': '60px',
                      'borderWidth': '1px', 'borderStyle': 'dashed',
                      'borderRadius': '5px', 'textAlign': 'center',
                      'margin-bottom': '10px'}, multiple=False),

    dbc.Button("Exportar CSV", id="btn-csv", color="secondary", disabled=True, className="mb-3"),
    dcc.Download(id="download-csv"),

    html.Hr(),

    html.Div(id='output-analise'),
    html.Div(id='wordcloud-output'),
    html.Div(id='word-frequency'),
    html.Div(id='texto-extraido', style={'whiteSpace': 'pre-wrap', 'overflowY': 'scroll', 'height': '300px',
                                         'border': '1px solid #ddd', 'padding': '10px', 'marginTop': '20px'})
], fluid=True)

def extrair_texto(file_content):
    doc = fitz.open(stream=file_content, filetype="pdf")
    return ''.join([pagina.get_text() for pagina in doc]).strip()

def resumo_automatico(texto):
    frases = [f.strip() for f in texto.split('.') if f.strip()]
    return '. '.join(frases[:5]) + '.' if len(frases) >= 5 else texto

def analisar_sentimento(texto):
    texto_traduzido = texto.lower()
    for pt, en in TRADUCOES.items():
        texto_traduzido = texto_traduzido.replace(pt, en)
    analise = TextBlob(texto_traduzido)
    return {'polaridade': analise.sentiment.polarity, 'subjetividade': analise.sentiment.subjectivity}

def contar_palavras(texto, palavras):
    texto_lower = texto.lower()
    return {p: texto_lower.count(p) for p in palavras}

def gerar_nuvem(texto):
    wordcloud = WordCloud(width=800, height=400, background_color="white",
                          stopwords=STOPWORDS, collocations=False).generate(texto)
    img = io.BytesIO()
    wordcloud.to_image().save(img, format='PNG')
    img.seek(0)
    return 'data:image/png;base64,' + base64.b64encode(img.read()).decode()

def criar_grafico_frequencia(contagem):
    df = pd.DataFrame.from_dict(contagem, orient='index', columns=['Contagem']).sort_values('Contagem', ascending=False)
    fig = go.Figure(go.Bar(x=df.index, y=df['Contagem'], marker_color='blue'))
    fig.update_layout(title='Frequência de Palavras', xaxis_title='Palavras', yaxis_title='Contagem')
    return fig

global_data = {}

@app.callback(
    [Output('output-analise', 'children'),
     Output('wordcloud-output', 'children'),
     Output('word-frequency', 'children'),
     Output('texto-extraido', 'children'),
     Output('btn-csv', 'disabled')],
    Input('upload-pdf', 'contents'),
    State('upload-pdf', 'filename')
)
def processar_pdf(contents, filename):
    if not contents:
        return "", "", "", "", True

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    texto = extrair_texto(io.BytesIO(decoded))
    if not texto:
        return " Não foi possível extrair texto do PDF.", "", "", "", True

    resumo = resumo_automatico(texto)
    sentimento = analisar_sentimento(texto)
    contagem = contar_palavras(texto, PALAVRAS_CHAVE)
    wordcloud_img = gerar_nuvem(texto)
    fig_frequencia = criar_grafico_frequencia(contagem)

    global global_data
    global_data = {
        "filename": filename,
        "resumo": resumo,
        "sentimento": sentimento,
        "contagem": contagem,
        "texto": texto
    }

    return (
        html.Div([
            html.H5("Resumo da Ata:"),
            html.P(resumo),
            html.Hr(),
            html.H5("Sentimento:"),
            html.P(f"Polaridade: {sentimento['polaridade']:.3f}, Subjetividade: {sentimento['subjetividade']:.3f}")
        ]),
        html.Img(src=wordcloud_img, style={'width': '1900%', 'maxWidth': '1900px'}),
        dcc.Graph(figure=fig_frequencia),
        texto,
        False
    )

@app.callback(
    Output('download-csv', 'data'),
    Input('btn-csv', 'n_clicks'),
    prevent_initial_call=True
)
def exportar_csv(n):
    if not global_data or n is None:
        return dash.no_update

    dados = [
        ["Arquivo", global_data['filename']],
        ["Polaridade", f"{global_data['sentimento']['polaridade']:.3f}"],
        ["Subjetividade", f"{global_data['sentimento']['subjetividade']:.3f}"],
        ["Resumo", global_data['resumo']],
        [],
        ["Palavra", "Frequência"]
    ]
    for palavra, freq in global_data['contagem'].items():
        dados.append([palavra, freq])

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=',')
    writer.writerows(dados)
    buffer.seek(0)

    return dcc.send_string(buffer.getvalue(), filename=f"dados_{global_data['filename'].replace('.pdf', '')}.csv")

if __name__ == '__main__':
    app.run(debug=True)
