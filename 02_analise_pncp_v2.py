import pandas as pd
import glob
import os

print("Iniciando Análise de Anomalias - PNCP (V2) - 4 Filtros com Tetos Anuais")

TIPOS_IMPEDITIVOS = [
    'Impedimento/proibição de contratar com prazo determinado',
    'Impedimento/proibição de contratar sem prazo determinado',
    'Suspensão',
    'Declaração de Inidoneidade sem prazo determinado',
    'Declaração de Inidoneidade com prazo determinado',
    'Suspensão/Interdição das atividades sem prazo determinado',
]

# Teto móvel para Dispensa de Licitação (Art. 75 Lei 14.133) - Engenharia/Serviços
TETOS_DISPENSA = {
    2021: 100000.00,
    2022: 108041.15,
    2023: 114416.65,
    2024: 119812.02,
    2025: 125000.00,
    2026: 130000.00
}

print("Carregando Sanções (CEIS)...")
df_sancoes = pd.read_csv('../../etl/data/sanctions/ceis.csv', sep=',', encoding='latin-1', on_bad_lines='skip', low_memory=False)
cpf_cnpj_col = [c for c in df_sancoes.columns if 'CPF' in c.upper() or 'CNPJ' in c.upper()][0]
df_sancoes['cnpj_limpo'] = df_sancoes[cpf_cnpj_col].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)
df_sancoes['data_inicio_dt'] = pd.to_datetime(df_sancoes['data_inicio'], format='%d/%m/%Y', errors='coerce')
df_sancoes['data_fim_dt'] = pd.to_datetime(df_sancoes['data_fim'], format='%d/%m/%Y', errors='coerce')
df_sancoes_imp = df_sancoes[df_sancoes['tipo_sancao'].isin(TIPOS_IMPEDITIVOS)]

print("Carregando Contratos (referentes a 2021)...")
contratos_files = glob.glob("../../etl/data/pncp_contratos/pncp_2021*.json")
if contratos_files:
    df_pncp_contratos = pd.concat([pd.read_json(f) for f in contratos_files], ignore_index=True)
    df_pncp_contratos['numero_controle_compra'] = df_pncp_contratos['numeroControlePncpCompra']
    df_pncp_contratos['ni_limpo'] = df_pncp_contratos['niFornecedor'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)
else:
    df_pncp_contratos = pd.DataFrame()

# Processamento da Anomalia 4 que depende apenas dos contratos
total_sancao_vigente = 0
if not df_pncp_contratos.empty:
    merged_ceis = pd.merge(df_pncp_contratos, df_sancoes_imp, left_on='ni_limpo', right_on='cnpj_limpo')
    merged_ceis['data_ass_dt'] = pd.to_datetime(merged_ceis['dataAssinatura'], errors='coerce')
    fraude_ceis = merged_ceis[
        (merged_ceis['data_inicio_dt'] <= merged_ceis['data_ass_dt']) &
        (merged_ceis['data_fim_dt'].isna() | (merged_ceis['data_fim_dt'] >= merged_ceis['data_ass_dt']))
    ]
    fraude_ceis = fraude_ceis.drop_duplicates(subset=['numeroControlePNCP', 'ni_limpo'])
    total_sancao_vigente = len(fraude_ceis)


# Processamento em lotes das Compras (para não estourar a RAM)
compras_files = glob.glob("../../RobsonTCC/data/pncp/pncp_*.json")

total_cronologia_reversa = 0
total_aditivo_ilegal = 0
total_fuga_modalidade = 0

print(f"Processando {len(compras_files)} arquivos de compras para os outros 3 filtros...")

for idx, file in enumerate(compras_files, 1):
    df_compras = pd.read_json(file)
    if df_compras.empty:
        continue
        
    df_compras['numero_controle_compra'] = df_compras['numeroControlePNCP']
    df_compras['valor_estimado_compra'] = pd.to_numeric(df_compras['valorTotalEstimado'], errors='coerce')
    df_compras['ano_compra'] = pd.to_numeric(df_compras['anoCompra'], errors='coerce')
    
    # Anomalia 3: Licitação Montada (Fuga de Modalidade / Teto Móvel)
    dispensas = df_compras[df_compras['modalidadeId'] == 8.0]
    
    for ano, teto in TETOS_DISPENSA.items():
        anomalias_ano = dispensas[(dispensas['ano_compra'] == ano) & (dispensas['valor_estimado_compra'] > teto)]
        total_fuga_modalidade += len(anomalias_ano)
        
    # Anomalias 1 e 2 cruzando com contratos
    if not df_pncp_contratos.empty:
        df_cruzado = pd.merge(df_compras, df_pncp_contratos, on='numero_controle_compra', suffixes=('_compra', '_contrato'))
        if not df_cruzado.empty:
            # // ==============================================================================
            # // NOTA METODOLÓGICA / DESCOBERTA SOBRE 'valorTotalEstimado' NULO OU 0.0:
            # // Cerca de ~5% dos editais no PNCP apresentam 'valorTotalEstimado' ausente ou igual a 0.0.
            # // Motivos técnicos e jurídicos identificados:
            # // 1. Orçamento Sigiloso (Art. 24 da Lei 14.133/2021): O órgão público mantém o valor estimado
            # //    sob sigilo até a fase de lances para evitar o efeito "âncora" e estimular descontos reais.
            # // 2. Critério de Maior Desconto: Disputa percentual sobre tabelas (ex: SINAPI) sem valor monetário global.
            # // 3. Credenciamento: Contratação de múltiplos prestadores sem demanda global fechada a priori.
            # // 4. Limitação Técnica de Integração: Sistemas municipais que gravam valores nos itens e omitem no cabeçalho.
            # //
            # // IMPACTO NAS MÉTRICAS:
            # // Se 'valor_estimado <= 0', qualquer contrato positivo seria falsamente categorizado como
            # // sobrepreço / aditivo ilegal (> 1.25 * valor_estimado).
            # // A salvaguarda '(df_cruzado["valor_estimado"] > 0)' é MANDATÓRIA para evitar falsos positivos.
            # // ==============================================================================
            df_cruzado['valor_estimado'] = pd.to_numeric(df_cruzado['valorTotalEstimado'], errors='coerce')
            df_cruzado['valor_contratado'] = pd.to_numeric(df_cruzado['valorInicial'], errors='coerce')
            df_cruzado['data_abertura'] = pd.to_datetime(df_cruzado['dataAberturaProposta'], errors='coerce')
            df_cruzado['data_assinatura'] = pd.to_datetime(df_cruzado['dataAssinatura'], errors='coerce')
            
            # Anomalia 1: Cronologia Reversa
            cronologia = df_cruzado[df_cruzado['data_assinatura'] < df_cruzado['data_abertura']]
            total_cronologia_reversa += len(cronologia)
            
            # Anomalia 2: Distorções Financeiras (> 25% com valor estimado válido)
            aditivo = df_cruzado[
                (df_cruzado['valor_estimado'] > 0) & 
                (df_cruzado['valor_contratado'] > (df_cruzado['valor_estimado'] * 1.25))
            ]
            total_aditivo_ilegal += len(aditivo)

print("="*50)
print("RESUMO DE ANOMALIAS DETECTADAS NOS 4 FILTROS:")
print("="*50)
print(f"1. Cronologia Reversa (PNCP): {total_cronologia_reversa}")
print(f"2. Distorções Financeiras (> 25%): {total_aditivo_ilegal}")
print(f"3. Fuga de Modalidade/Licitação Montada Acima Teto (2021-2026): {total_fuga_modalidade}")
print(f"4. Sanção Vigente no CEIS (PNCP): {total_sancao_vigente}")
print("="*50)
print("Análise concluída.")
