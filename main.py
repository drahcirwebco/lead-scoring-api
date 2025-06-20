# main.py

import pandas as pd
import joblib
import re
from fastapi import FastAPI
from pydantic import BaseModel

# --- Carregar os artefatos salvos ---
# Carrega o modelo treinado e a lista de colunas esperada.
model = joblib.load('lead_scorer_model.pkl')
model_columns = joblib.load('model_columns.pkl')
print("Modelo e colunas carregados com sucesso.")

# Inicializa o aplicativo FastAPI
app = FastAPI(title="API de Lead Scoring", version="1.0.0")


# --- Definir o formato dos dados de entrada ---
# Pydantic garante que os dados recebidos pela API tenham o formato correto.
class LeadData(BaseModel):
    valor: float
    utm_campaign: str = 'desconhecido'
    utm_content: str = 'desconhecido'
    utm_medium: str = 'desconhecido'
    utm_source: str = 'desconhecido'
    utm_term: str = 'desconhecido'


# --- Criar o endpoint de predição ---
@app.post("/predict")
def predict(data: LeadData):
    """
    Recebe os dados de um novo lead, processa-os e retorna a probabilidade de ganho.
    """
    # 1. Converter os dados recebidos em um DataFrame do Pandas
    input_df = pd.DataFrame([data.dict()])

    # 2. Aplicar o One-Hot Encoding para as UTMs
    input_df = pd.get_dummies(input_df, columns=['utm_campaign', 'utm_content', 'utm_medium', 'utm_source', 'utm_term'])

    # 3. Alinhar as colunas com as que o modelo foi treinado
    # Cria um DataFrame vazio com as colunas do modelo e preenche com os dados de entrada.
    # Colunas que estão no modelo mas não na entrada viram 0.
    # Colunas que estão na entrada mas não no modelo são ignoradas.
    final_df = pd.DataFrame(columns=model_columns)
    final_df = pd.concat([final_df, input_df], ignore_index=True, sort=False).fillna(0)
    
    # 4. Garantir que a ordem das colunas seja a mesma do treinamento
    # Adiciona a coluna 'ciclo_em_dias', que não existe para um lead novo (usamos 0)
    final_df['ciclo_em_dias'] = 0
    final_df = final_df[model_columns]

    # 5. >>> CORREÇÃO XGBOOST <<<
    # Sanitizar os nomes das colunas da mesma forma que fizemos no treino
    regex = re.compile(r"\[|\]|<", re.IGNORECASE)
    final_df.columns = [regex.sub("_", col) if any(x in str(col) for x in set(('[', ']', '<'))) else col for col in final_df.columns.values]

    # 6. Fazer a predição
    probability = model.predict_proba(final_df)[:, 1][0]

    # 7. Retornar o resultado
    return {
        "lead_score_probability": float(probability),
        "prediction_label": "Ganho Provável" if probability > 0.7 else ("Potencial Médio" if probability > 0.4 else "Perda Provável")
    }


# --- Endpoint de "saúde" da API (opcional, mas boa prática) ---
@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Lead Scoring está no ar!"}