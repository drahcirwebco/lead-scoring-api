# main.py (Versão de TESTE com segurança do webhook simplificada)

import pandas as pd
import joblib
import re
import os
import requests
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

# --- Carregar Artefatos e Configurações ---
model = joblib.load('lead_scorer_model.pkl')
model_columns = joblib.load('model_columns.pkl')

PIPEDRIVE_API_KEY = os.getenv('PIPEDRIVE_API_KEY')
LEAD_SCORE_FIELD_KEY = os.getenv('LEAD_SCORE_FIELD_KEY')
WEBHOOK_USER = os.getenv('WEBHOOK_USER')
WEBHOOK_PASSWORD = os.getenv('WEBHOOK_PASSWORD')

TARGET_PIPELINE_ID = 1

app = FastAPI(title="API de Lead Scoring em Tempo Real", version="2.3.0-debug-auth")
security = HTTPBasic()

# ==============================================================================
#           >> FUNÇÃO DE SEGURANÇA TEMPORARIAMENTE SIMPLIFICADA <<
# ==============================================================================
# Esta versão da função de segurança sempre retorna True.
# Ela serve para testar se o resto do sistema funciona, isolando o problema 401.
# ATENÇÃO: Não use esta versão em produção a longo prazo.

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    ATENÇÃO: Versão de teste que sempre permite o acesso.
    Isso é apenas para diagnosticar o problema 401.
    """
    print(">>> AVISO DE SEGURANÇA: Autenticação de webhook está em modo de teste (sempre permitindo).")
    # A função simplesmente retorna True, bypassando a verificação de usuário e senha.
    return True
# ==============================================================================


# --- Função de Lógica de Predição ---
def get_prediction_for_deal(deal_data: dict) -> float:
    """Recebe um dicionário com dados de um negócio e retorna a probabilidade de ganho."""
    input_df = pd.DataFrame([deal_data])
    input_df_dummies = pd.get_dummies(input_df, columns=['utm_campaign', 'utm_content', 'utm_medium', 'utm_source', 'utm_term'])
    
    final_df = pd.DataFrame(columns=model_columns).fillna(0)
    final_df = pd.concat([final_df, input_df_dummies], ignore_index=True, sort=False).fillna(0)
    final_df['ciclo_em_dias'] = 0
    final_df = final_df[model_columns]

    regex = re.compile(r"\[|\]|<", re.IGNORECASE)
    final_df.columns = [regex.sub("_", col) for col in final_df.columns.values]

    probability = model.predict_proba(final_df)[:, 1][0]
    return float(probability)

# --- Função para Atualizar o Pipedrive de volta ---
def update_pipedrive_deal(deal_id: int, score: float):
    """Atualiza o campo customizado no Pipedrive com o novo score."""
    if not all([PIPEDRIVE_API_KEY, LEAD_SCORE_FIELD_KEY]):
        print("AVISO: API Key ou Field Key não configurados. Pipedrive não será atualizado.")
        return

    url = f"https://api.pipedrive.com/v1/deals/{deal_id}?api_token={PIPEDRIVE_API_KEY}"
    payload = {LEAD_SCORE_FIELD_KEY: round(score * 100, 2)}
    
    try:
        response = requests.put(url, json=payload)
        response.raise_for_status()
        print(f"Pipedrive: Negócio {deal_id} atualizado com score {payload[LEAD_SCORE_FIELD_KEY]}%.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO ao atualizar o Pipedrive para o negócio {deal_id}: {e}")

# --- ENDPOINT PRINCIPAL: Webhook do Pipedrive ---
@app.post("/webhook/pipedrive")
async def pipedrive_webhook(request: Request, authenticated: bool = Depends(verify_credentials)):
    """Recebe notificações do Pipedrive, filtra pelo funil correto, calcula o score e atualiza o negócio."""
    if not authenticated:
        # Com a função de teste, esta parte nunca será executada, mas a mantemos por estrutura.
        raise HTTPException(status_code=401, detail="Autenticação falhou.")

    webhook_data = await request.json()
    deal_info = webhook_data.get("current", {})
    deal_id = deal_info.get("id")
    pipeline_id = deal_info.get("pipeline_id")

    if not deal_id:
        return {"status": "ok", "message": "Evento sem ID de negócio, ignorado."}

    if pipeline_id != TARGET_PIPELINE_ID:
        print(f"Negócio {deal_id} está no funil {pipeline_id}, não no funil alvo {TARGET_PIPELINE_ID}. Ignorando.")
        return {"status": "ok", "message": f"Negócio ignorado (funil {pipeline_id})."}

    print(f"Negócio {deal_id} recebido do funil alvo. Processando...")

    deal_for_model = {
        "valor": deal_info.get("value", 0) or 0,
        "utm_source": deal_info.get("utm_source", "desconhecido"),
        "utm_medium": deal_info.get("utm_medium", "desconhecido"),
        "utm_campaign": deal_info.get("utm_campaign", "desconhecido"),
        "utm_content": deal_info.get("utm_content", "desconhecido"),
        "utm_term": deal_info.get("utm_term", "desconhecido"),
    }

    probability = get_prediction_for_deal(deal_for_model)
    update_pipedrive_deal(deal_id, probability)
    
    return {"status": "ok", "message": f"Negócio {deal_id} processado com sucesso."}

# Endpoint de "saúde" da API para verificar se está no ar
@app.get("/")
def read_root():
    return {"status": "ok", "message": "API de Lead Scoring em Tempo Real está no ar!"}

# O endpoint de debug foi removido nesta versão, pois a simplificação da segurança já é um teste mais direto.