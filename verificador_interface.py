import streamlit as st
from verificador_air import validar_taxas_origem_freight
from verificador_lcl import validar_lcl_armazenagem

st.set_page_config(page_title="Verificador de Cotações", page_icon="🧾", layout="wide")

st.markdown('<h2 style="font-weight:700">Verificador de Cotações</h2>', unsafe_allow_html=True)
st.markdown('<div style="color:#6f85ad;font-size:1.09rem;">Sistema de verificação de cotações</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([3, 2, 3])

with col2:
    opcao = st.selectbox(
        "Tipo:",
        ["-- Selecione --", "Importação Aérea", "Importação Marítima LCL"],
        index=0
    )

if opcao != "-- Selecione --":
    with st.form("form_codigo"):
        col1, col2, col3 = st.columns([3, 2, 3])
        with col2:
            codigo = st.text_input("🔎 Código da cotação:", placeholder="Ex: 15521")
            enviar = st.form_submit_button("Validar")

        if enviar and codigo.strip():
            with st.spinner("Validando cotação..."):
                if opcao == "Importação Aérea":
                    resultado = validar_taxas_origem_freight(codigo.strip())
                elif opcao == "Importação Marítima LCL":
                    resultado = validar_lcl_armazenagem(codigo.strip())
                else:
                    resultado = ["❌ Opção inválida."]

            st.subheader("Resultado da Validação")
            for linha in resultado:
                if linha.startswith("✅"):
                    st.success(linha)
                elif linha.startswith("❌"):
                    st.error(linha)
                elif linha.startswith("ℹ️"):
                    st.info(linha)
                else:
                    st.warning(linha)

st.markdown("---")
st.markdown(
    '<div style="text-align:center;color:#aaa;font-size:1.04rem;">'
    "Verificador de cotações - open source | Não usar em produção sem revisão de segurança"
    "</div>",
    unsafe_allow_html=True
)
