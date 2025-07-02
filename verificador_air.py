import pymysql
import os
from dotenv import load_dotenv
import datetime

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

def is_bit_on(val):
    return val in (b'\x01', 1, True)

def is_bit_off(val):
    return val in (b'\x00', 0, False, None)

def validar_taxas_origem_freight(code):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as e:
        return [f"❌ Erro ao conectar no banco: {e}"]

    relatorio = []
    try:
        cursor.execute("""
            SELECT ID, MODAL, IS_SHOW_SPREAD, IS_SHOW_ONLY_ITENS_WITH_SAME_CONTACT, DATE_ALERT_SELLER, CONSIGNEE_CONTACT_GENERAL_FK, IS_SHOW_ESTIMATED_IOF
            FROM M0205_QUOTATION
            WHERE CODE = %s
        """, (code,))
        cotacao = cursor.fetchone()
        if not cotacao:
            return ["❌ Cotação não encontrada para o CODE informado."]

        # MODAL
        if cotacao.get("MODAL") != "AIR_IMPORT":
            relatorio.append("ℹ️ Este verificador só se aplica a cotações de importação aérea (AIR_IMPORT).")
            return relatorio

        # --- VOLUMES ---
        cursor.execute("""
            SELECT *
            FROM M0205_QUOTATION_VOLUME
            WHERE QUOTATION_FK = %s
        """, (cotacao["ID"],))
        volumes = cursor.fetchall()
        if not volumes:
            relatorio.append("❌ Aba VOLUMES: É obrigatório preencher pelo menos um volume.")
        else:
            for idx, vol in enumerate(volumes, start=1):
                if not vol.get('VOL_QUANTITY'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe a quantidade de volumes (campo 'Quantidade').")
                if not vol.get('VOL_LENGTH'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe o comprimento.")
                if not vol.get('VOL_HEIGHT'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe a altura.")
                if not vol.get('VOL_WIDTH'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe a largura.")
                if not vol.get('CUBED_WEIGHT'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe o peso cubado (volume).")
                if not vol.get('UNIT_WEIGHT'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe o peso unitário.")
                if not vol.get('TOTAL_WEIGHT'):
                    relatorio.append(f"❌ Aba VOLUMES - volume {idx}: Informe o peso total.")

        # --- FLAGS ---
        if cotacao.get("IS_SHOW_SPREAD") != b'\x01':
            relatorio.append("❌ Na importação aérea, o campo 'Exibir spread' deve estar flegado.")
        if cotacao.get("IS_SHOW_ONLY_ITENS_WITH_SAME_CONTACT") != b'\x01':
            relatorio.append("❌ Na importação aérea, o campo 'Exibir somente itens do contato' deve estar flegado.")
        if not is_bit_on(cotacao.get("IS_SHOW_ESTIMATED_IOF")):
            relatorio.append("❌ Na importação aérea, o campo 'Exibir IOF Estimado' deve estar flegado.")

        # --- DATA ALERTA VENDEDOR ---
        if cotacao.get("DATE_ALERT_SELLER"):
            alerta_vendedor = cotacao.get("DATE_ALERT_SELLER")
            if isinstance(alerta_vendedor, str):
                alerta_vendedor = alerta_vendedor[:10]
                alerta_vendedor = datetime.datetime.strptime(alerta_vendedor, "%Y-%m-%d").date()
            elif isinstance(alerta_vendedor, datetime.datetime):
                alerta_vendedor = alerta_vendedor.date()
            hoje = datetime.date.today()
            if alerta_vendedor < hoje:
                relatorio.append("❌ O campo 'Alerta vendedor' deve ser hoje ou uma data futura.")

        # --- ITENS ---
        cursor.execute("""
            SELECT ID, IS_SHOW_IN_DOCUMENT, IS_SHOW_BOARD_INSTRUCTION, BUY_TYPE, SALE_TYPE, RATE_TYPE,
                   SERVICE_FK, IS_TO_SEND, FREIGHT_VALUE_TYPE, IS_NOT_TO_SALE, PROVIDER_TYPE_SALE,
                   BUY_TOTAL, PROVIDER_TYPE, SERVICE_DESCRIPTION, BUY_RATE, SALE_RATE, FREQUENCY_TYPE, VIA, TRANSIT_TIME, PORT_ORIGIN_FK, PORT_DESTINATION_FK
            FROM M0205_QUOTATION_ITEM
            WHERE QUOTATION_FK = %s
        """, (cotacao["ID"],))
        itens = cursor.fetchall()
        if not itens:
            relatorio.append("ℹ️ Nenhuma taxa encontrada para esta cotação.")
        freight_itens = [i for i in itens if (i.get("RATE_TYPE") or "").upper() == "FREIGHT"]
        algum_freight_com_origem = any(f.get('PORT_ORIGIN_FK') for f in freight_itens)
        algum_freight_com_destino = any(f.get('PORT_DESTINATION_FK') for f in freight_itens)
        for item in itens:
            # FREIGHT
            if item.get("RATE_TYPE") == 'FREIGHT':
                if not item.get("FREQUENCY_TYPE"):
                    relatorio.append(f"❌ Na taxa FREIGHT ({item.get('SERVICE_DESCRIPTION')}), o campo Frequência está vazio.")
                if not item.get("VIA"):
                    relatorio.append(f"❌ Na taxa FREIGHT ({item.get('SERVICE_DESCRIPTION')}), o campo Via está vazio.")
                if not item.get("TRANSIT_TIME"):
                    relatorio.append(f"❌ Na taxa FREIGHT ({item.get('SERVICE_DESCRIPTION')}), o campo Transit Time está vazio.")
                if not item.get("PORT_ORIGIN_FK") and not algum_freight_com_origem:
                    relatorio.append(f"❌ Na taxa FREIGHT ({item.get('SERVICE_DESCRIPTION')}), o campo Origem está vazio.")
                if not item.get("PORT_DESTINATION_FK") and not algum_freight_com_destino:
                    relatorio.append(f"❌ Na taxa FREIGHT ({item.get('SERVICE_DESCRIPTION')}), o campo Destino está vazio.")
                compra_pp = (str(item.get("BUY_TYPE") or "").upper() == "PP")
                venda_pp = (str(item.get("SALE_TYPE") or "").upper() == "PP")
                if compra_pp and venda_pp:
                    if not is_bit_on(item.get("IS_SHOW_IN_DOCUMENT")):
                        relatorio.append(
                            "❌ Na taxa FREIGHT (PP/PP), o campo 'MOSTRAR NO DOCUMENTO' deve estar flegado."
                        )
                    if not is_bit_off(item.get("IS_SHOW_BOARD_INSTRUCTION")):
                        relatorio.append(
                            "❌ Na taxa FREIGHT (PP/PP), o campo 'MOSTRAR NO E-MAIL INSTRUÇÃO' deve estar desflegado."
                        )
                else:
                    if not is_bit_on(item.get("IS_SHOW_IN_DOCUMENT")):
                        relatorio.append(
                            "❌ Na taxa FREIGHT, o campo 'MOSTRAR NO DOCUMENTO' está desflegado."
                        )
                    if not is_bit_on(item.get("IS_SHOW_BOARD_INSTRUCTION")):
                        relatorio.append(
                            "❌ Na taxa FREIGHT, o campo 'MOSTRAR NO E-MAIL INSTRUÇÃO' está desflegado."
                        )

            # Profit (SERVICE_FK = 33)
            if item.get("SERVICE_FK") == 33:
                if not is_bit_off(item.get("IS_SHOW_IN_DOCUMENT")):
                    relatorio.append(
                        "❌ Para a taxa de profit, o campo 'MOSTRAR NO DOCUMENTO' deve estar desflegado."
                    )
                if not is_bit_off(item.get("IS_TO_SEND")):
                    relatorio.append(
                        "❌ Para a taxa de profit, o campo 'ENVIAR' deve estar desflegado."
                    )
                if not is_bit_on(item.get("IS_SHOW_BOARD_INSTRUCTION")):
                    relatorio.append(
                        "❌ Para a taxa de profit, o campo E-MAIL 'INSTRUÇÃO DE EMBARQUE' deve estar flegado."
                    )
                if not is_bit_on(item.get("IS_NOT_TO_SALE")):
                    relatorio.append(
                        "❌ Para a taxa de profit, o campo 'Não Faturar' deve estar flegado."
                    )
                buy_rate = float(item.get("BUY_RATE") or 0)
                sale_rate = float(item.get("SALE_RATE") or 0)
                if buy_rate <= 0 or sale_rate != 0:
                    relatorio.append(
                        f"❌ Para a taxa de profit ({item.get('SERVICE_DESCRIPTION')}), deve existir tarifa de compra (> 0) e NÃO pode existir tarifa de venda (> 0)."
                    )

            # Origem (ORIGIN, exceto SERVICE_FK = 33)
            if item.get("RATE_TYPE") == 'ORIGIN' and item.get("SERVICE_FK") != 33:
                if (item.get("FREIGHT_VALUE_TYPE") or '').upper() != 'DUE_AGENT':
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')} ({item.get('SERVICE_DESCRIPTION')}), o campo devido deve ser Total Other Charges Due Agent."
                    )

            # DESTINATION, exceto IOF
            if item.get("RATE_TYPE") == 'DESTINATION' and item.get("SERVICE_FK") != 44:
                if item.get("SERVICE_FK") == 48:
                    if (item.get("FREIGHT_VALUE_TYPE") or '').upper() != 'DUE_CARRIER':
                        relatorio.append(
                            f"❌ Na taxa de destino ({item.get('SERVICE_DESCRIPTION')}), o campo devido deve ser 'Total Other Charges Due Carrier'."
                        )
                else:
                    if (item.get("FREIGHT_VALUE_TYPE") or '').upper() != 'VALUATION_CHARGE':
                        relatorio.append(
                            f"❌ Na taxa de destino ({item.get('SERVICE_DESCRIPTION')}), o campo devido deve ser 'Valuation charge'."
                        )

            # IOF de destino (SERVICE_FK = 44)
            if item.get("SERVICE_FK") == 44 and item.get("RATE_TYPE") == 'DESTINATION':
                if (item.get("FREIGHT_VALUE_TYPE") or '').upper() != 'TAX':
                    relatorio.append(
                        f"❌ Para a taxa de IOF de destino, o campo devido deve ser taxa. [Taxa: {item.get('SERVICE_DESCRIPTION')}]"
                    )

            # DESTINATION: tipo de venda deve ser CLIENTE
            if item.get("RATE_TYPE") == 'DESTINATION':
                if (item.get("PROVIDER_TYPE_SALE") or '').upper() != 'CUSTOMER':
                    relatorio.append(
                        "❌ Na taxa de destino, o campo 'Tipo de venda' deve ser Cliente."
                    )
                if (
                    (item.get("BUY_TOTAL") == 0 or item.get("BUY_TOTAL") == 0.0)
                    and item.get("PROVIDER_TYPE") is not None
                    and str(item.get("PROVIDER_TYPE")).strip() != ''
                ):
                    relatorio.append(
                        f"⚠️ Atenção: Quando a tarifa de compra é zerada, o campo 'Tipo de fornecedor' deve estar vazio. [Taxa: {item.get('SERVICE_DESCRIPTION')}]"
                    )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"❌ Para a taxa de destino, o campo 'ENVIAR' deve estar flegado. [Taxa: {item.get('SERVICE_DESCRIPTION')}]"
                    )

        if not relatorio and itens:
            relatorio.append("✅ Cotação aprovada para ser enviada.")

    except Exception as ex:
        relatorio.append(f"❌ Erro ao executar verificação: {ex}")

    finally:
        try:
            conn.close()
        except:
            pass

    return relatorio

if __name__ == "__main__":
    codigo = input("Digite o código da cotação: ")
    erros = validar_taxas_origem_freight(codigo.strip())
    for linha in erros:
        print(linha)
