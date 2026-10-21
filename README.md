# Automated Anomaly Detection in Brazilian Public Procurement

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![DuckDB](https://img.shields.io/badge/Engine-DuckDB-yellow.svg)](https://duckdb.org/)

Reproduction package and audit pipelines for the empirical study on data integrity, opacity, and normative violations in Brazilian public procurement repositories: the federal **Portal Nacional de Contratações Públicas (PNCP)** and the multi-state municipal dataset **Método de Integração de Dados para Fiscalização (MIDES)**, cross-referenced with federal sanctions from the **Cadastro de Empresas Inidôneas e Suspensas (CEIS)**.

---

## 📌 Repository Overview

This repository provides reproducible scripts and notebooks to execute 4 legal-normative audit rules over millions of public procurement records:

1. **Reverse Chronology**: Contracts signed before the official proposal opening/publication date (violating Art. 17 of Brazilian Procurement Law 14.133/2021).
2. **Financial Distortion (Overpricing)**: Contracts exceeding estimated budget by more than 25% ($\frac{V_{\text{contract}} - V_{\text{est}}}{V_{\text{est}}} > 0.25$, bounded by Art. 125 of Law 14.133/2021).
3. **Direct Award Threshold Evasion**: Direct procurements/waivers (*dispensa de licitação*) exceeding legal annual statutory ceilings (Decree 12.343/2024 and predecessor limits).
4. **Active Debarment Sanctions**: Contracts celebrated with suppliers undergoing active legal prohibitions to contract with public administration registered in CEIS (Art. 87 of Law 8.666/1993 and Art. 156 of Law 14.133/2021).

---

## 🗂️ File Structure

| File | Description |
| :--- | :--- |
| `01_extracao.py` | Reference data ingestion routines via government open APIs. |
| `02_analise_pncp.py` | High-performance DuckDB/Pandas pipeline to audit the 4 rules across federal PNCP records. |
| `03_analise_mides.py` | Audit pipeline to detect anomalies across 1.54M municipal contracts from MIDES. |
| `Reproducao_Resultados_Artigo.ipynb` | Unified Jupyter Notebook for end-to-end execution, visualizations, and comparative tables. |
| `requirements.txt` | Python runtime dependencies. |

---

## 🚀 Quickstart

### 1. Environment Setup

```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Running Audits

To audit the federal PNCP dataset:
```bash
python 02_analise_pncp.py
```

To audit the municipal MIDES dataset:
```bash
python 03_analise_mides.py
```

Or run the interactive notebook:
```bash
jupyter notebook Reproducao_Resultados_Artigo.ipynb
```

---

## ⚖️ Legal Grounding & Methodology

- **Sanctions Filter (CEIS)**: Only definitive impediment and debarment categories (*Inidoneidade*, *Suspensão*, *Impedimento*) are considered. Warnings or administrative fines without contracting barriers are filtered out.
- **Floating Ceilings**: Annual adjustment factors applied for direct procurement thresholds across 2021-2026.
- **Estimated Budget Safeguard**: Only tenders with valid positive estimated budgets ($V_{\text{est}} > 0$) are evaluated for financial distortion, avoiding false positives caused by confidential budgets (Art. 24 of Law 14.133/2021).

---

## 📄 Citation

```bibtex
@inproceedings{mendes2026anomalias,
  title     = {Detecção Automatizada de Anomalias em Compras Públicas Brasileiras: Uma Análise Exploratória da Integridade de Dados Abertos},
  author    = {Mendes, Francisco Robson Queiroz and Magalhães, Regis Pires},
  booktitle = {Encontros Universitários da UFC},
  year      = {2026}
}
```
