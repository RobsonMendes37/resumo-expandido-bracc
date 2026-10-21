import pandas as pd

print("Iniciando Análise de Anomalias - MIDES")

MIDES_DIR = '../../etl/data/mides'

# 1. Carregar Dados
df_mides_lic = pd.read_csv(f'{MIDES_DIR}/licitacao.csv', low_memory=False)
df_mides_ctr = pd.read_csv(f'{MIDES_DIR}/contrato.csv', low_memory=False)

df_lic_unique = df_mides_lic[['licitacao_id', 'estado', 'modalidade', 'valor_estimado', 'data_publicacao']].drop_duplicates(subset=['licitacao_id'])
df_ctr_unique = df_mides_ctr[['licitacao_id', 'valor', 'cnpj_fornecedor', 'data_assinatura']].drop_duplicates(subset=['licitacao_id', 'cnpj_fornecedor'])

# Tratamento de Tipos e Datas
df_lic_unique['valor_estimado'] = pd.to_numeric(df_lic_unique['valor_estimado'], errors='coerce')
df_ctr_unique['valor'] = pd.to_numeric(df_ctr_unique['valor'], errors='coerce')
df_lic_unique['data_publicacao'] = pd.to_datetime(df_lic_unique['data_publicacao'], errors='coerce')
df_ctr_unique['data_assinatura'] = pd.to_datetime(df_ctr_unique['data_assinatura'], errors='coerce')

# INNER JOIN Edital -> Contrato
df_audit = pd.merge(df_lic_unique, df_ctr_unique, on='licitacao_id', how='inner')
df_audit = df_audit.dropna(subset=['valor_estimado', 'valor'])

# Remove outliers irreais para a métrica financeira
df_audit_fin = df_audit[(df_audit['valor_estimado'] > 1000) & (df_audit['valor'] > 1000) & (df_audit['valor'] < 50e9)]

# --- ANOMALIAS ---

# 1. Cronologia Reversa
df_crono = df_audit.dropna(subset=['data_publicacao', 'data_assinatura'])
fraude_temporal = df_crono[df_crono['data_assinatura'] < df_crono['data_publicacao']]
print(f"Anomalia: Cronologia Reversa (MIDES) = {len(fraude_temporal)}")

# 2. Distorções Financeiras (Sobrepreço > 25% e <= 200%, e contrato > 10.000 para remover outliers)
df_audit_fin['sobrepreco_pct'] = ((df_audit_fin['valor'] - df_audit_fin['valor_estimado']) / df_audit_fin['valor_estimado'] * 100)
aditivos_ilegais = df_audit_fin[(df_audit_fin['sobrepreco_pct'] > 25) & (df_audit_fin['sobrepreco_pct'] <= 200) & (df_audit_fin['valor'] > 10000)]
print(f"Anomalia: Distorções Financeiras (MIDES) = {len(aditivos_ilegais)}")

# 3. Fuga de Modalidade / Teto de Dispensa
def limite_dispensa(ano):
    if pd.isna(ano) or ano <= 2018: return 15000.00
    elif ano == 2019: return 33000.00
    elif ano in [2020, 2021]: return 100000.00
    elif ano == 2022: return 108041.15
    elif ano == 2023: return 114416.65
    elif ano == 2024: return 119812.02
    elif ano == 2025: return 125451.15
    else: return 130984.20

df_audit['ano_assinatura'] = df_audit['data_assinatura'].dt.year
df_audit['teto_dispensa'] = df_audit['ano_assinatura'].apply(limite_dispensa)

# Modalidade 8.0 = Dispensa
dispensas_irregulares = df_audit[(df_audit['modalidade'] == 8.0) & (df_audit['valor'] > df_audit['teto_dispensa'])]
print(f"Anomalia: Fuga de Modalidade (MIDES) = {len(dispensas_irregulares)}")

# 4. Sanção Vigente (CEIS)
TIPOS_IMPEDITIVOS = [
    'Impedimento/proibição de contratar com prazo determinado',
    'Impedimento/proibição de contratar sem prazo determinado',
    'Suspensão',
    'Declaração de Inidoneidade sem prazo determinado',
    'Declaração de Inidoneidade com prazo determinado',
    'Suspensão/Interdição das atividades sem prazo determinado',
]

df_sancoes = pd.read_csv('../../etl/data/sanctions/ceis.csv', sep=',', encoding='latin-1', on_bad_lines='skip', low_memory=False)
cpf_cnpj_col = [c for c in df_sancoes.columns if 'CPF' in c.upper() or 'CNPJ' in c.upper()][0]
df_sancoes['cnpj_limpo'] = df_sancoes[cpf_cnpj_col].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)
df_sancoes['data_inicio'] = pd.to_datetime(df_sancoes['data_inicio'], dayfirst=True, errors='coerce')
df_sancoes['data_fim'] = pd.to_datetime(df_sancoes['data_fim'], dayfirst=True, errors='coerce')
df_sancoes_imp = df_sancoes[df_sancoes['tipo_sancao'].isin(TIPOS_IMPEDITIVOS)]

df_ctr_unique['cnpj_fornecedor'] = df_ctr_unique['cnpj_fornecedor'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)

df_audit_ceis = pd.merge(df_ctr_unique, df_sancoes_imp, left_on='cnpj_fornecedor', right_on='cnpj_limpo', how='inner')
fraude_ceis_ativa = df_audit_ceis[
    (df_audit_ceis['data_assinatura'] >= df_audit_ceis['data_inicio']) &
    ((df_audit_ceis['data_assinatura'] <= df_audit_ceis['data_fim']) | df_audit_ceis['data_fim'].isna())
]
fraude_ceis_ativa = fraude_ceis_ativa.drop_duplicates(subset=['licitacao_id', 'cnpj_fornecedor'])

print(f"Anomalia: Sanção Vigente no CEIS (MIDES) = {len(fraude_ceis_ativa)}")

print("Análise concluída.")
