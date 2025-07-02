# Verificador de Cotações (LCL & Aéreo)

## 📋 Objetivo

Este sistema foi desenvolvido para **automatizar a verificação de regras operacionais em cotações de importação** (modal marítimo LCL e aéreo), auxiliando times comerciais, operacionais e analistas de pricing a detectar rapidamente inconsistências, campos obrigatórios não preenchidos e inconformidades antes do envio ao cliente.

## 🚀 Como Funciona

O sistema realiza validações automáticas conectando-se ao banco de dados (MySQL), checando cotações a partir de um código informado pelo usuário.  
Após a consulta, é gerado um relatório em tempo real apontando:
- Falta de campos obrigatórios
- Inconsistências de datas e flags
- Erros em parâmetros de cada taxa (Frete, Seguro, IOF, Desconsolidação, etc)
- Divergências específicas por tipo de modal ou serviço

A interface é simples, via navegador, utilizando [Streamlit](https://streamlit.io/).

---


## 🛠️ Instalação e Uso

1. **Clone o repositório:**
   ```bash
   git clone (https://github.com/ferreira-me/VERIFICADOR_COTACAO.git)
   cd nome-do-repo
