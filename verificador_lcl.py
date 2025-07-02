import pymysql
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def is_checked(val):
    return (
        str(val)
        in ("1", "True", "true", "b'\\x01'", "b'1'", "b'\\x01\\x00'", "b'\\x01'")
        or val == 1
    )


def is_bit_on(value):
    if isinstance(value, bytes):
        return value != b"\x00" and value != b""
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.strip() in ("1", "True", "true")
    return bool(value)


def validar_lcl_armazenagem(codigo):
    relatorio = []
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT ID, MODAL, IS_SHOW_SPREAD, IS_SHOW_ONLY_ITENS_WITH_SAME_CONTACT,
            DATE_CREATION, DATE_VALIDITY, DATETIME_SENT, DATE_ALERT_SELLER, CARRIER_FK, IS_SHOW_ESTIMATED_IOF
            FROM M0205_QUOTATION
            WHERE CODE = %s
        """,
            (codigo,),
        )

        cotacao = cursor.fetchone()
        if not cotacao:
            relatorio.append("Cotação não encontrada para o código informado.")
            return relatorio

            # ----- VOLUMES (Obrigatório preencher) -----
        cursor.execute(
            """
            SELECT *
            FROM M0205_QUOTATION_VOLUME
            WHERE QUOTATION_FK = %s
        """,
            (cotacao["ID"],),
        )
        volumes = cursor.fetchall()
        if not volumes:
            relatorio.append(
                "❌ Aba VOLUMES: É obrigatório preencher pelo menos um volume."
            )
        else:
            for idx, vol in enumerate(volumes, start=1):
                if not vol.get("VOL_QUANTITY"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe a quantidade de volumes (campo 'Quantidade')."
                    )
                if not vol.get("VOL_LENGTH"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe o comprimento."
                    )
                if not vol.get("VOL_HEIGHT"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe a altura."
                    )
                if not vol.get("VOL_VOLUME"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe a largura."
                    )
                if not vol.get("CUBED_WEIGHT"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe o peso cubado (volume)."
                    )
                if not vol.get("UNIT_WEIGHT"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe o peso unitário."
                    )
                if not vol.get("TOTAL_WEIGHT"):
                    relatorio.append(
                        f"❌ Aba VOLUMES - volume {idx}: Informe o peso total."
                    )

        # ----- DATAS (Regras cruzadas) -----
        def to_date(val):
            if isinstance(val, datetime):
                return val.date()
            try:
                return datetime.strptime(str(val), "%Y-%m-%d").date()
            except:
                return None

        date_creation = to_date(cotacao.get("DATE_CREATION"))
        date_validity = to_date(cotacao.get("DATE_VALIDITY"))
        datetime_sent = cotacao.get("DATETIME_SENT")
        date_alert_seller = to_date(cotacao.get("DATE_ALERT_SELLER"))

        if date_creation and date_validity and date_validity < date_creation:
            relatorio.append(
                "❌ Na aba GERAL: A data de validade (DATE_VALIDITY) não pode ser anterior à data de criação (DATE_CREATION)."
            )
        if datetime_sent and date_validity and datetime_sent.date() > date_validity:
            relatorio.append(
                "❌ Na aba GERAL: A data de envio (DATETIME_SENT) não pode ser posterior à data de validade (DATE_VALIDITY)."
            )
        if (
            datetime_sent
            and date_alert_seller
            and date_alert_seller < datetime_sent.date()
        ):
            relatorio.append(
                "❌ Na aba GERAL: A data de alerta ao vendedor (DATE_ALERT_SELLER) deve ser igual ou posterior à data de envio (DATETIME_SENT)."
            )

        # ----- MODAL / FLAGS -----
        if cotacao["MODAL"] != "MARITIME_IMPORT":
            relatorio.append("A cotação informada não é do tipo MARITIME_IMPORT.")
            return relatorio
        if not is_checked(cotacao.get("IS_SHOW_SPREAD", 0)):
            relatorio.append(
                "❌ Na importação marítima, o campo 'Exibir spread' deve estar flegado."
            )
        if not is_checked(cotacao.get("IS_SHOW_ONLY_ITENS_WITH_SAME_CONTACT")):
            relatorio.append(
                "❌ Na importação marítima, o campo 'Exibir somente itens do contato' deve estar flegado."
            )
        if not is_bit_on(cotacao.get("IS_SHOW_ESTIMATED_IOF")):
            relatorio.append(
                "❌ Na importação marítima, o campo 'Exibir IOF Estimado' deve estar flegado."
            )

        # ----- ITENS -----
        cursor.execute(
            """
            SELECT *
            FROM M0205_QUOTATION_ITEM
            WHERE QUOTATION_FK = %s
        """,
            (cotacao["ID"],),
        )
        itens = cursor.fetchall()

        if not itens:
            relatorio.append("Nenhum item encontrado para a cotação.")
            return relatorio

        existe_lcl = any(item.get("SERVICE_FK") == 16 for item in itens)
        if not existe_lcl:
            relatorio.append("Cotação não é LCL")
            return relatorio

        # ---- Variáveis auxiliares ----
        sale_rate_estimativa = None
        for i in itens:
            if i.get("SERVICE_FK") == 37:
                try:
                    sale_rate_estimativa = float(i.get("SALE_RATE") or 0)
                except:
                    sale_rate_estimativa = None
                break

        # ---- REGRAS POR TIPO DE TAXA ----
        for item in itens:
            # 1 - Estimativa de Armazenagem
            if item.get("SERVICE_FK") == 37:
                if not is_bit_on(item.get("IS_NOT_TO_SALE")):
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Não Faturar' precisa estar marcado."
                    )
                if not is_bit_on(item.get("IS_NOT_TO_PURCHASE")):
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Não Pagar' precisa estar marcado."
                    )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' precisa estar marcado."
                    )

            # 2 - Comissão sobre Armazenagem (DESTINATION)
            if (
                item.get("SERVICE_FK") == 100
                and (item.get("RATE_TYPE") or "").upper() == "DESTINATION"
            ):
                if is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' deve estar desmarcado."
                    )
                if not is_bit_on(item.get("IS_NOT_TO_PURCHASE")):
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Não Pagar' precisa estar marcado."
                    )
                if sale_rate_estimativa is not None:
                    try:
                        sale_rate_100 = float(item.get("SALE_RATE") or 0)
                    except:
                        sale_rate_100 = None
                    if sale_rate_100 != sale_rate_estimativa:
                        relatorio.append(
                            f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A tarifa de venda deve ser igual à da Estimativa de Armazenagem."
                        )
                if int(item.get("MEASURE_UNIT_FK") or 0) != 9:
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A unidade de medida deve ser porcentagem."
                    )
                if (item.get("RATE_TYPE") or "").upper() != "DESTINATION":
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo Tipo de Taxa deve ser DESTINATION."
                    )
                try:
                    sale_quantity = float(item.get("SALE_QUANTITY") or 0)
                except Exception:
                    sale_quantity = 0
                if cotacao["CARRIER_FK"] in [890, 2043, 2]:
                    if item["SALE_QUANTITY"] not in [30, 30.0, 30.000, 30000]:
                        relatorio.append(
                            "❌ Quando o Carrier for CRAFT, a taxa Comissão sobre armazenagem deve ter quantidade de venda igual a 30%."
                        )
                else:
                    if item["SALE_QUANTITY"] != 40.000:
                        relatorio.append(
                            "❌ Na taxa de DESTINATION, verificar Comissão sobre armazenagem: a quantidade de venda deve ser 40%."
                        )
                try:
                    buy_rate = float(item.get("BUY_RATE") or 0)
                except Exception:
                    buy_rate = 0
                if buy_rate != 0:
                    relatorio.append(
                        f"❌ Na taxa de {item.get('RATE_TYPE')}, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A tarifa de compra deve ser zerada."
                    )

            # 3 - Desconsolidação (DESTINATION, OHPERS)
            if (
                item.get("SERVICE_FK") == 43
                and (item.get("RATE_TYPE") or "").upper() == "DESTINATION"
            ):
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"⚠️ Na taxa de DESTINATION, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' deve estar marcado. Desconsiderar em casos de negociações especiais."
                    )
                if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                    relatorio.append(
                        f"❌ Na taxa de DESTINATION, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A unidade de medida deve ser 'per shipment'."
                    )
                service_desc = (item.get("SERVICE_DESCRIPTION") or "").upper()
                if (
                    "OHPERS" in service_desc
                    and int(item.get("CONTACT_GENERAL_FK") or 0) != 51
                ):
                    relatorio.append(
                        f"❌ Na taxa de DESTINATION, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O contato geral deve ser OHPERS."
                    )
                if not item.get("SALE_CURRENCY_FK"):
                    relatorio.append(
                        f"❌ Na taxa de DESTINATION, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A moeda de venda precisa estar preenchida."
                    )
                if "OHPERS" in service_desc and item.get("BUY_CURRENCY_FK") != 17:
                    relatorio.append(
                        "❌ Na taxa de Desconsolidação, a moeda de compra deve ser BRL."
                    )
                buy_rate = float(item.get("BUY_RATE") or 0)
                if "OHPERS" in service_desc and round(buy_rate, 2) != 130.40:
                    relatorio.append(
                        "❌ Na taxa de Desconsolidação, a tarifa de compra deve ser exatamente 130,40."
                    )

            # 4 - Seguro (DESTINATION, SALE_RATE >= 40.00)
            if (
                item.get("SERVICE_FK") == 31
                and (item.get("RATE_TYPE") or "").upper() == "DESTINATION"
            ):
                try:
                    sale_rate = float(item.get("SALE_RATE") or 0)
                except Exception:
                    sale_rate = 0
                if sale_rate < 40.00:
                    relatorio.append(
                        f"⚠️ Na taxa de DESTINATION, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A tarifa de venda deve ser no mínimo 40,00. Desconsiderar em casos de negociações especiais."
                    )

            # 5 - IOF (DESTINATION, BUY_RATE == SALE_RATE)
            if item.get("SERVICE_FK") == 44:
                rate_type = (item.get("RATE_TYPE") or "").upper()
                if rate_type != "DESTINATION":
                    relatorio.append(
                        f"❌ Na taxa IOF, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo Tipo de Taxa deve ser 'DESTINATION'."
                    )
                try:
                    buy_rate = float(item.get("BUY_RATE") or 0)
                    sale_rate = float(item.get("SALE_RATE") or 0)
                except Exception:
                    buy_rate = sale_rate = None
                if buy_rate != sale_rate:
                    relatorio.append(
                        f"❌ Na taxa IOF, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O valor da tarifa de compra deve ser igual ao valor da tarifa de venda."
                    )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"⚠️ Na taxa IOF, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' deve estar marcado. Desconsiderar em casos de negociações especiais."
                    )
                if (item.get("PROVIDER_TYPE") or "").upper() == "CUSTOMER" and int(
                    item.get("CONTACT_GENERAL_FK") or 0
                ) != 98:
                    relatorio.append(
                        f"❌ Na taxa IOF, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: Quando o fornecedor for CUSTOMER, o contato geral deve ser B&T CORRETORA."
                    )

            # 6 - Taxas de Origem (SERVICE_FK == 92 e RATE_TYPE == ORIGIN)
            if (
                item.get("SERVICE_FK") == 92
                and (item.get("RATE_TYPE") or "").upper() == "ORIGIN"
            ):
                service_name = item.get("SERVICE_DESCRIPTION") or "Taxa de Origem"
                provider_type = (item.get("PROVIDER_TYPE") or "").upper()
                buy_type = (item.get("BUY_TYPE") or "").upper()
                if provider_type == "AGENT" and buy_type != "PP":
                    relatorio.append(
                        f"❌ Na taxa de ORIGIN, verificar a taxa {service_name}: Quando o fornecedor for AGENTE, o tipo de compra deve ser PP."
                    )
                if provider_type == "MARITIMEAGENCY" and buy_type != "CC":
                    relatorio.append(
                        f"❌ Na taxa de ORIGIN, verificar a taxa {service_name}: Quando o fornecedor for AGÊNCIA MARÍTIMA, o tipo de compra deve ser CC."
                    )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"❌ Na taxa de ORIGIN, verificar a taxa {service_name}: O campo 'Enviar' deve estar marcado."
                    )
                if not is_bit_on(item.get("IS_SHOW_BOARD_INSTRUCTION")):
                    relatorio.append(
                        f"❌ Na taxa de ORIGIN, verificar a taxa {service_name}: O campo 'Mostrar no e-mail Instrução Embarque' deve estar marcado."
                    )
                if not is_bit_on(item.get("IS_SHOW_IN_DOCUMENT")):
                    relatorio.append(
                        f"❌ Na taxa de ORIGIN, verificar a taxa {service_name}: O campo 'Mostrar no documento' deve estar marcado."
                    )

            # 7 - THD - Terminal Handling Destination
            if item.get("SERVICE_FK") == 325:
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' deve estar marcado."
                    )
                if (item.get("PROVIDER_TYPE") or "").upper() != "MARITIMEAGENCY":
                    relatorio.append(
                        f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O tipo de fornecedor deve ser 'MARITIMEAGENCY'."
                    )
                try:
                    buy_total = float(item.get("BUY_TOTAL") or 0)
                except Exception:
                    buy_total = None
                if buy_total is not None:
                    if buy_total < 20:
                        if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                            relatorio.append(
                                f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: Se o total de compra for menor que 20, a unidade de medida deve ser 'Per Shipment'."
                            )
                    else:
                        if int(item.get("MEASURE_UNIT_FK") or 0) != 2:
                            relatorio.append(
                                f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: Se o total de compra for maior que 20, a unidade de medida deve ser 'Per ton ou cubic meter'."
                            )
                contato = int(item.get("CONTACT_GENERAL_FK") or 0)
                try:
                    buy_rate = float(item.get("BUY_RATE") or 0)
                except Exception:
                    buy_rate = None
                if contato in [453, 1424, 1691, 4411, 4467] and buy_rate != 20:
                    relatorio.append(
                        f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: Quando o contato é um dos IDs [453, 1424, 1691, 4411, 4467], a tarifa de compra deve ser 20."
                    )
                elif contato in [2, 890, 2043] and buy_rate != 30:
                    relatorio.append(
                        f"❌ Na taxa THD, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: Quando o contato é um dos IDs [2, 890, 2043], a tarifa de compra deve ser 30."
                    )

            # 8 - BL FEE
            if item.get("SERVICE_FK") == 70:
                rate_type = (item.get("RATE_TYPE") or "").upper()
                provider_type = (item.get("PROVIDER_TYPE") or "").upper()
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"⚠️ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo 'Enviar' deve estar marcado. Desconsiderar em casos de negociações especiais."
                    )
                try:
                    sale_rate = float(item.get("SALE_RATE") or 0)
                except Exception:
                    sale_rate = 0
                if sale_rate == 0:
                    relatorio.append(
                        f"⚠️ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A tarifa de venda deve ser diferente de zero. Desconsiderar em casos de negociações especiais."
                    )
                if rate_type != "DESTINATION":
                    relatorio.append(
                        f"❌ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O campo Tipo de Taxa deve ser 'DESTINATION'."
                    )
                if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                    relatorio.append(
                        f"❌ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: A unidade de medida deve ser 'per shipment'."
                    )
                if provider_type not in ("MARITIMEAGENCY", ""):
                    relatorio.append(
                        f"❌ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O tipo de fornecedor deve ser 'MARITIMEAGENCY' ou estar em branco."
                    )
                if provider_type == "":
                    relatorio.append(
                        f"⚠️ Na taxa BL FEE, verificar a taxa {item.get('SERVICE_DESCRIPTION')}: O tipo de fornecedor está em branco. Desconsiderar em casos de negociações especiais com Co-loader."
                    )

            # 9 - Courrier
            if item.get("SERVICE_FK") == 74:
                service_name = item.get("SERVICE_DESCRIPTION") or "Courrier"
                if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                    relatorio.append(
                        f"❌ Na taxa Courrier, verificar a taxa {service_name}: Unidade de medida deve ser 'per shipment' (4)."
                    )
                if (item.get("PROVIDER_TYPE") or "").upper() != "AIRLINE":
                    relatorio.append(
                        f"❌ Na taxa Courrier, verificar a taxa {service_name}: Tipo de fornecedor deve ser 'AIRLINE'."
                    )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"⚠️ Na taxa Courrier, verificar a taxa {service_name}: Campo 'Enviar' deve estar marcado. Desconsiderar em casos de negociações especiais."
                    )
                try:
                    sale_rate = float(item.get("SALE_RATE") or 0)
                except Exception:
                    sale_rate = 0
                if sale_rate < 55:
                    relatorio.append(
                        f"⚠️ Na taxa Courrier, verificar a taxa {service_name}: Tarifa de venda deve ser no mínimo 55. Desconsiderar em casos de negociações especiais."
                    )
                try:
                    buy_rate = float(item.get("BUY_RATE") or 0)
                except Exception:
                    buy_rate = 0
                if buy_rate < 55:
                    relatorio.append(
                        f"⚠️ Na taxa Courrier, verificar a taxa {service_name}: Tarifa de compra deve ser no mínimo 55. Desconsiderar em casos de negociações especiais."
                    )
                if int(item.get("SALE_CURRENCY_FK") or 0) != 7:
                    relatorio.append(
                        f"❌ Na taxa Courrier, verificar a taxa {service_name}: Moeda de venda deve ser USDT (7)."
                    )
                if int(item.get("BUY_CURRENCY_FK") or 0) != 7:
                    relatorio.append(
                        f"❌ Na taxa Courrier, verificar a taxa {service_name}: Moeda de compra deve ser USDT (7)."
                    )
                if (item.get("RATE_TYPE") or "").upper() != "DESTINATION":
                    relatorio.append(
                        f"❌ Na taxa Courrier, verificar a taxa {service_name}: Tipo de taxa (RATE_TYPE) deve ser 'DESTINATION'."
                    )

            # 10 - Frete (SERVICE_FK == 16)
            if item.get("SERVICE_FK") == 16:
                service_name = item.get("SERVICE_DESCRIPTION") or "Frete"
                if (item.get("PROVIDER_TYPE") or "").upper() != "MARITIMEAGENCY":
                    relatorio.append(
                        f"Na taxa Frete, verificar a taxa {service_name}: Tipo de fornecedor deve ser 'MARITIMEAGENCY'."
                    )
                try:
                    buy_quantity = float(item.get("BUY_QUANTITY") or 0)
                except:
                    buy_quantity = 0
                if buy_quantity <= 1:
                    if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                        relatorio.append(
                            f"❌ Na taxa Frete, verificar a taxa {service_name}: Quantidade de compra <= 1 exige unidade 'Per Shipment'."
                        )
                else:
                    if int(item.get("MEASURE_UNIT_FK") or 0) != 2:
                        relatorio.append(
                            f"❌ Na taxa Frete, verificar a taxa {service_name}: Quantidade de compra > 1 exige unidade 'Per Ton'."
                        )
                try:
                    sale_quantity = float(item.get("SALE_QUANTITY") or 0)
                except:
                    sale_quantity = 0
                if sale_quantity <= 1:
                    if int(item.get("MEASURE_UNIT_FK") or 0) != 4:
                        relatorio.append(
                            f"❌ Na taxa Frete, verificar a taxa {service_name}: Quantidade de venda <= 1 exige unidade 'Per Shipment'."
                        )
                else:
                    if int(item.get("MEASURE_UNIT_FK") or 0) != 2:
                        relatorio.append(
                            f"❌ Na taxa Frete, verificar a taxa {service_name}: Quantidade de venda > 1 exige unidade 'Per Ton'."
                        )
                campos_obrigatorios = [
                    ("PORT_ORIGIN_FK", "Origem"),
                    ("PORT_DESTINATION_FK", "Destino"),
                    ("VIA", "Via"),
                    ("FREE_TIME_DEMURRAGE_BUY", "Free Time Compra"),
                    ("FREE_TIME_DEMURRAGE", "Free Time Venda"),
                    ("TRANSIT_TIME", "Transit Time"),
                    ("FREQUENCY_TYPE", "Frequência"),
                    ("FINAL_DESTINATION", "Destino Final"),
                ]
                for campo, nome in campos_obrigatorios:
                    if not item.get(campo):
                        relatorio.append(
                            f"⚠️ Na taxa Frete, verificar a taxa {service_name}: O campo '{nome}' precisa estar preenchido. Desconsiderar em casos de negociações especiais."
                        )
                if not is_bit_on(item.get("IS_TO_SEND")):
                    relatorio.append(
                        f"⚠️ Na taxa Frete, verificar a taxa {service_name}: O campo 'Enviar' deve estar marcado. Desconsiderar em casos de negociações especiais."
                    )
                if not is_bit_on(item.get("IS_SHOW_BOARD_INSTRUCTION")):
                    relatorio.append(
                        f"❌ Na taxa Frete, verificar a taxa {service_name}: O campo 'Mostrar no e-mail Instrução Embarque' deve estar marcado."
                    )
                if not is_bit_on(item.get("IS_SHOW_IN_DOCUMENT")):
                    relatorio.append(
                        f"❌ Na taxa Frete, verificar a taxa {service_name}: O campo 'Mostrar no Documento' deve estar marcado."
                    )
                if not is_bit_on(item.get("IS_SHOW_IN_DOCUMENT_MASTER")):
                    relatorio.append(
                        f"❌ Na taxa Frete, verificar a taxa {service_name}: O campo 'Mostrar no Doc. Master termos técnicos' deve estar marcado."
                    )

        # ---- REGRAS GERAIS FORA DO LOOP ----
        if cotacao.get("CARRIER_FK") in [890, 2043, 2]:
            qtd_desconsolidacao = sum(1 for i in itens if i["SERVICE_FK"] == 43)
            if qtd_desconsolidacao != 2:
                relatorio.append(
                    "❌ Quando o Carrier for CRAFT, devem existir exatamente 2 linhas com o serviço Desconsolidação."
                )

        if not relatorio:
            relatorio.append("✅ Cotação aprovada para ser enviada.")

    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return relatorio


if __name__ == "__main__":
    codigo = input("Digite o código da cotação: ")
    erros = validar_lcl_armazenagem(codigo.strip())
    for linha in erros:
        print(linha)
