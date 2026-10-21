#!/usr/bin/env python3
"""
BR-ACC: Audit and Anomaly Detection in Federal Public Procurement (PNCP)
Applies 4 normative audit filters over open procurement data cross-referenced with CEIS sanctions.

Filters:
1. Reverse Chronology (Contract signed prior to tender proposal opening)
2. Financial Distortion (Contract value exceeding 25% over estimated value)
3. Direct Award Threshold Evasion (Waiver exceeding annual legal threshold)
4. Active Sanction (Contract signed during supplier sanction period in CEIS)
"""

import os
import glob
import time
import duckdb
import pandas as pd

# Legal threshold limits for direct procurement (Art. 75 Lei 14.133 / Federal Decrees)
ANNUAL_DIRECT_AWARD_THRESHOLDS = {
    2021: 100000.00,
    2022: 108041.15,
    2023: 114416.65,
    2024: 119812.02,
    2025: 125000.00,
    2026: 130000.00,
}

DEBARMENT_SANCTION_TYPES = [
    'Impedimento/proibição de contratar com prazo determinado',
    'Impedimento/proibição de contratar sem prazo determinado',
    'Suspensão',
    'Declaração de Inidoneidade sem prazo determinado',
    'Declaração de Inidoneidade com prazo determinado',
    'Suspensão/Interdição das atividades sem prazo determinado',
]

def locate_data_paths():
    base_candidates = [
        ".",
        "..",
        "../..",
        "/media/robson/Secundario LINUX/Robson linux Secundario/Arquivos-Linux/Faculdade/TCC/br-acc"
    ]
    
    ceis_path = None
    contratos_glob = None
    compras_glob = None
    
    for base in base_candidates:
        c_path = os.path.join(base, "etl/data/sanctions/ceis.csv")
        if os.path.isfile(c_path):
            ceis_path = c_path
            break
            
    for base in base_candidates:
        # Full dataset paths
        full_contratos = glob.glob(os.path.join(base, "RobsonTCC/data/pncp_contratos/pncp_*.json"))
        full_compras = glob.glob(os.path.join(base, "RobsonTCC/data/pncp/pncp_*.json"))
        if len(full_contratos) > 10:
            contratos_glob = os.path.join(base, "RobsonTCC/data/pncp_contratos/pncp_*.json")
            compras_glob = os.path.join(base, "RobsonTCC/data/pncp/pncp_*.json")
            break
            
        # Sample dataset paths
        sample_contratos = glob.glob(os.path.join(base, "etl/data/pncp_contratos/pncp_*.json"))
        sample_compras = glob.glob(os.path.join(base, "etl/data/pncp/pncp_*.json"))
        if sample_contratos and not contratos_glob:
            contratos_glob = os.path.join(base, "etl/data/pncp_contratos/pncp_*.json")
            compras_glob = os.path.join(base, "etl/data/pncp/pncp_*.json")

    return ceis_path, contratos_glob, compras_glob

def run_duckdb_audit(ceis_path, contratos_glob, compras_glob):
    t0 = time.time()
    con = duckdb.connect()
    con.execute('SET threads TO 4;')
    con.execute('SET max_memory = "6GB";')

    print(f"Loading debarment sanctions from: {ceis_path}")
    con.execute(f"""
        CREATE TABLE ceis AS 
        SELECT 
            lpad(regexp_replace(COALESCE(cpf_cnpj, ''), '[^0-9]', '', 'g'), 14, '0') as cnpj_limpo,
            data_inicio,
            data_fim,
            tipo_sancao
        FROM read_csv('{ceis_path}', 
                      delim=',', 
                      encoding='latin-1', 
                      ignore_errors=true, 
                      header=true)
        WHERE tipo_sancao IN (
            'Impedimento/proibição de contratar com prazo determinado',
            'Impedimento/proibição de contratar sem prazo determinado',
            'Suspensão',
            'Declaração de Inidoneidade sem prazo determinado',
            'Declaração de Inidoneidade com prazo determinado',
            'Suspensão/Interdição das atividades sem prazo determinado'
        )
        AND regexp_replace(COALESCE(cpf_cnpj, ''), '[^0-9]', '', 'g') != ''
        AND length(regexp_replace(COALESCE(cpf_cnpj, ''), '[^0-9]', '', 'g')) >= 11;
    """)
    ceis_count = con.execute("SELECT count(*) FROM ceis").fetchone()[0]
    print(f"-> Active debarment sanctions loaded: {ceis_count:,}")

    print(f"Mapping Contracts from: {contratos_glob}")
    con.execute(f"""
        CREATE VIEW v_contratos AS
        SELECT 
            numeroControlePNCP as id_contrato,
            numeroControlePncpCompra as id_compra,
            TRY_CAST(anoContrato AS INTEGER) as ano_contrato,
            TRY_CAST(dataAssinatura AS DATE) as data_assinatura,
            TRY_CAST(valorInicial AS DOUBLE) as valor_contratado,
            lpad(regexp_replace(COALESCE(niFornecedor, ''), '[^0-9]', '', 'g'), 14, '0') as ni_limpo
        FROM read_json('{contratos_glob}', 
                       columns={{
                           'numeroControlePNCP': 'VARCHAR',
                           'numeroControlePncpCompra': 'VARCHAR',
                           'anoContrato': 'VARCHAR',
                           'dataAssinatura': 'VARCHAR',
                           'valorInicial': 'VARCHAR',
                           'niFornecedor': 'VARCHAR'
                       }});
    """)

    print(f"Mapping Tenders/Purchases from: {compras_glob}")
    con.execute(f"""
        CREATE VIEW v_compras AS
        SELECT 
            numeroControlePNCP as id_compra,
            TRY_CAST(anoCompra AS INTEGER) as ano_compra,
            TRY_CAST(dataAberturaProposta AS DATE) as data_abertura,
            TRY_CAST(valorTotalEstimado AS DOUBLE) as valor_estimado,
            TRY_CAST(modalidadeId AS DOUBLE) as modalidade_id
        FROM read_json('{compras_glob}', 
                       columns={{
                           'numeroControlePNCP': 'VARCHAR',
                           'anoCompra': 'VARCHAR',
                           'dataAberturaProposta': 'VARCHAR',
                           'valorTotalEstimado': 'VARCHAR',
                           'modalidadeId': 'VARCHAR'
                       }});
    """)

    print("\nAuditing Filter 4: Active Debarment Sanction (CEIS)...")
    res_sancao = con.execute("""
        SELECT count(DISTINCT c.id_contrato)
        FROM v_contratos c
        INNER JOIN ceis s ON c.ni_limpo = s.cnpj_limpo
        WHERE c.data_assinatura IS NOT NULL
          AND s.data_inicio <= c.data_assinatura
          AND (s.data_fim IS NULL OR s.data_fim >= c.data_assinatura);
    """).fetchone()[0]

    print("Auditing Filter 3: Direct Award Threshold Evasion (Art. 75)...")
    res_dispensa = con.execute("""
        SELECT count(*) 
        FROM v_compras
        WHERE modalidade_id = 8.0
          AND (
              (ano_compra = 2021 AND valor_estimado > 100000.00) OR
              (ano_compra = 2022 AND valor_estimado > 108041.15) OR
              (ano_compra = 2023 AND valor_estimado > 114416.65) OR
              (ano_compra = 2024 AND valor_estimado > 119812.02) OR
              (ano_compra = 2025 AND valor_estimado > 125000.00) OR
              (ano_compra >= 2026 AND valor_estimado > 130000.00) OR
              (ano_compra IS NULL AND valor_estimado > 125451.15)
          );
    """).fetchone()[0]

    print("Auditing Filters 1 & 2 via Tender-Contract Cross-referencing...")
    res_cruzamento = con.execute("""
        SELECT 
            count(*) as total_cruzados,
            count(CASE WHEN c.data_assinatura < comp.data_abertura THEN 1 END) as cronologia_reversa,
            count(CASE WHEN comp.valor_estimado > 0 AND c.valor_contratado > (comp.valor_estimado * 1.25) THEN 1 END) as distorcao_financeira
        FROM v_contratos c
        INNER JOIN v_compras comp ON c.id_compra = comp.id_compra;
    """).fetchone()

    total_cruzados = res_cruzamento[0]
    total_cronologia = res_cruzamento[1]
    total_distorcao = res_cruzamento[2]
    total_anomalias = total_cronologia + total_distorcao + res_dispensa + res_sancao

    print("\n" + "="*65)
    print("FEDERAL PROCUREMENT AUDIT RESULTS (PNCP):")
    print("="*65)
    print(f"Total Matched Contracts (Tender-Contract): {total_cruzados:,}")
    print(f"1. Reverse Chronology (Signature < Opening): {total_cronologia:,} ({(total_cronologia/total_cruzados*100):.2f}%)")
    print(f"2. Financial Distortion (>25% over estimate): {total_distorcao:,} ({(total_distorcao/total_cruzados*100):.2f}%)")
    print(f"3. Direct Award Threshold Evasion:           {res_dispensa:,}")
    print(f"4. Active Debarment Sanction (CEIS):         {res_sancao:,}")
    print(f"Total Anomalies Detected:                    {total_anomalias:,}")
    print(f"Execution completed in: {time.time()-t0:.2f} seconds")
    print("="*65)

if __name__ == "__main__":
    ceis_path, contratos_glob, compras_glob = locate_data_paths()
    if not ceis_path or not contratos_glob or not compras_glob:
        print("Data files not found in standard paths. Please verify dataset directories.")
    else:
        run_duckdb_audit(ceis_path, contratos_glob, compras_glob)
