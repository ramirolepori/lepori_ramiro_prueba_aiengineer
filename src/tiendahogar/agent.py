"""Agente de soporte de TiendaHogar.

Orden de decisión (lo crítico es determinístico; el LLM solo redacta):
1. Inyección de prompt en la entrada: se rechaza sin llamar al modelo.
2. Guardrail de escalamiento (reembolso > $500, trato, facturación, legal): se deriva a un humano sin llamar al modelo.
3. Tool `consultar_estado_pedido` por cada ORD-XXXX mencionado.
4. RAG con umbral. Si no hay documento relevante ni pedido, responde que no tiene esa información.
5. Redacción: con LLM (solo con el contexto recuperado) o, sin LLM, citando los documentos tal cual.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from . import guardrails
from .llm import LLM, ErrorLLM
from .plazos import (PLAZO_DEVOLUCION_DIAS, dias_desde_la_compra, garantia_de, garantia_del_producto, nota_de_devolucion,
                     respuesta_de_garantia)
from .pedidos import consultar_estado_pedido, extraer_identificadores_raros, extraer_referencias
from .config import Config
from .embeddings import ClienteEmbeddings
from .lugares import confirmacion, resolver_lugares, respuesta_envio, respuesta_envio_sin_lugar
from .recuerdos import anotar, clave_del_recuerdo, responder_recuerdo
from .rag import IndiceBM25, RecuperadorHibrido, Resultado as ResultadoRAG, crear_recuperador, tokenizar, _PIDE_CANAL
from .sesion import (MAX_TURNOS, PREGUNTA_ANTIGUEDAD, PREGUNTA_MONTO, PREGUNTA_RECLAMO, TIEMPO, Sesion, dice_si_o_no, interpretar,
                     pregunta_pendiente, recordar_pregunta, retomar)
from .semantica import INTENCIONES, ClasificadorSemantico, crear_clasificador, segmentar
from .tiempos import Cronometro, activar, etapa
from .conversacion import es_agradecimiento, es_despedida, es_saludo
from .intenciones import (ACCION_QUE_NO_PUEDE, COMPRA_FUTURA, COMPRA_PROPIA, ENVIO_EXPLICITO, HABLA_DE_PLATA, INTENCION_ENVIO, INTERNACIONAL,
                          NO_DEVOLVIBLE, NOMBRA_EL_DOCUMENTO, OBJETO_DE_COMPRA, PIDE_COPIA, PIDE_COSTO, QUIERE_DEVOLVER, TAREA_AJENA,
                          TEMA_DE_ESTADO, TEMA_DE_POLITICA, dice_sin_comprobante, pide_reembolso, pregunta_por_su_compra)
from .mensajes import (AVISO_SIN_COSTO, MENSAJE_AGRADECIMIENTO, MENSAJE_BLOQUEO, MENSAJE_DESPEDIDA, MENSAJE_SALUDO, MENSAJE_SIN_ACCIONES,
                       MENSAJE_SIN_INFO, MENSAJE_VACIO, PREGUNTA_FECHA_COMPRA, TEXTO_CANAL)
from .redaccion import (SISTEMA, armar_prompt, completar_cobertura, limpiar_citas, notas_obligatorias, para_el_cliente, pedir_numero,
                        problema_de_salida, redactar_offline)

_CANDADO_TRAZAS = threading.Lock()
MAX_CARACTERES = 2000


@dataclass
class Respuesta:
    texto: str
    estado: str                                   # respondido | escalado | sin_informacion | bloqueado
    fuentes: list[str] = field(default_factory=list)
    escalamientos: list[str] = field(default_factory=list)
    pedidos: list[dict[str, Any]] = field(default_factory=list)
    traza: list[dict[str, Any]] = field(default_factory=list)
    conversacional: bool = False                  # charla (saludo, un dato ya dicho): no cambia lo que el agente esperaba del cliente
    tiempos: dict[str, float] = field(default_factory=dict)   # ms por etapa y por balde (ver tiempos.py)


class AgenteSoporte:
    def __init__(self, indice: IndiceBM25 | RecuperadorHibrido | None = None, llm: LLM | None = None, trazas_dir: Path | None = None,
                 clasificador: ClasificadorSemantico | None = None):
        config = Config()
        # un solo cliente de embeddings para el recuperador y el clasificador: cada texto se pide una vez
        cliente = ClienteEmbeddings(config) if config.embedding_model and config.proveedor == "openai" else None
        self.indice = indice or crear_recuperador(config, cliente)
        self.llm = llm
        self.trazas_dir = trazas_dir
        self.cliente_embeddings = cliente
        # reglas + capa semántica (embeddings si hay EMBEDDING_MODEL, si no n-gramas de caracteres)
        self.clasificador = clasificador or crear_clasificador(config, cliente)

    def responder(self, pregunta: str, sesion: Sesion | None = None) -> Respuesta:
        """Sin `sesion`, cada pregunta es independiente. Con una, el agente recuerda qué dato le pidió al cliente (ver sesion.py)."""
        if not isinstance(pregunta, str):
            pregunta = "" if pregunta is None else str(pregunta)
        traza_id, t0 = uuid.uuid4().hex[:12], time.perf_counter()
        traza: list[dict[str, Any]] = []

        def ev(tipo: str, **datos: Any) -> None:
            traza.append({"traza": traza_id, "t_ms": round((time.perf_counter() - t0) * 1000, 1),
                          "tipo": tipo, **datos})

        cron = Cronometro()
        previo = replace(sesion) if sesion is not None and sesion.pendiente else None
        with activar(cron):
            r = self._decidir(pregunta, ev, sesion)
        if sesion is not None:
            # dijo otra cosa que no tiene que ver con la tienda: se le contesta eso y se vuelve a pedir lo que faltaba
            if (previo is not None and not sesion.pendiente and (r.estado == "sin_informacion" or r.conversacional)
                    and retomar(sesion, previo)):
                r.texto = r.texto + chr(10) * 2 + pregunta_pendiente(sesion)
            recordar_pregunta(sesion, r.texto)
            if r.estado != "bloqueado" and not r.conversacional:
                anotar(sesion.datos, pregunta)
        total_ms = (time.perf_counter() - t0) * 1000
        r.tiempos = cron.resumen(total_ms, cron.embeddings_s * 1000, cron.embeddings_n)
        ev("fin", estado=r.estado, fuentes=r.fuentes, tiempos=r.tiempos)
        r.traza = traza
        if self.trazas_dir:
            self._guardar(traza)
        return r

    def _decidir(self, pregunta: str, ev: Callable[..., None], sesion: Sesion | None = None) -> Respuesta:
        pregunta = pregunta.strip()
        ev("entrada", chars=len(pregunta))
        if not pregunta:
            return Respuesta(MENSAJE_VACIO, "sin_informacion")
        if len(pregunta) > MAX_CARACTERES:
            # una consulta de soporte no necesita más: se evita trabajar (y pedir embeddings) sobre textos enormes
            ev("entrada_recortada", chars=len(pregunta), maximo=MAX_CARACTERES)
            pregunta = pregunta[:MAX_CARACTERES]

        if guardrails.detectar_inyeccion(pregunta):
            ev("guardrail", categoria="inyeccion")
            return Respuesta(MENSAJE_BLOQUEO, "bloqueado")

        # Con sesión: si el mensaje responde a lo que se le preguntó, se arma la consulta completa y sigue el flujo normal
        lugar_dado, repreguntar = None, True
        if sesion is not None and sesion.pendiente:
            if es_despedida(pregunta):
                sesion.limpiar()           # se despide: ya no espera nada
            elif (es_saludo(pregunta) or es_agradecimiento(pregunta)) and not dice_si_o_no(pregunta):
                # lo natural es contestar el saludo y volver a pedir lo que faltaba
                sesion.turnos += 1
                if sesion.turnos <= MAX_TURNOS:
                    ev("cortesia_con_pendiente", pendiente=sesion.pendiente)
                    if es_saludo(pregunta):
                        return Respuesta(f"¡Hola! {pregunta_pendiente(sesion)}", "respondido")
                    return Respuesta(f"¡De nada! {pregunta_pendiente(sesion)}", "respondido")
                sesion.limpiar()
        if sesion is not None and sesion.pendiente and guardrails.evaluar(pregunta, self.clasificador):
            sesion.limpiar()           # un mensaje para derivar (legal, trato...) no es la respuesta al dato pendiente
        if sesion is not None:
            turno = interpretar(sesion, pregunta)
            if turno is not None:
                ev("sesion", repregunta=bool(turno.repregunta), lugar=bool(turno.lugar))
                if turno.derivar:                     # el cliente confirmó que quiere hacer un reclamo
                    return Respuesta(guardrails._mensaje(turno.derivar)[1], "escalado", escalamientos=[turno.derivar])
                if turno.repregunta:
                    return Respuesta(turno.repregunta, "respondido")
                pregunta, lugar_dado, repreguntar = turno.consulta, turno.lugar, turno.repreguntar

        with etapa("guardrail"):
            escalamientos = guardrails.evaluar(pregunta, self.clasificador)
        if escalamientos:
            if sesion is not None:
                sesion.limpiar()           # se deriva a una persona: no queda nada pendiente
            ev("guardrail", categorias=[e.categoria for e in escalamientos],
               origenes=[e.origen for e in escalamientos], capa=self.clasificador.nombre,
               respaldo=self.clasificador.ultimo_respaldo)
            # varios casos a la vez se derivan al mismo canal: alcanza con el mensaje del primero
            derivacion = escalamientos[0].mensaje
            parcial = self._responder_parte_permitida(pregunta, ev, [e.categoria for e in escalamientos])
            if parcial is not None:
                texto, fuentes, pedidos = parcial
                return Respuesta(texto + "\n\n" + derivacion, "escalado", fuentes,
                                 [e.categoria for e in escalamientos], pedidos)
            return Respuesta(derivacion, "escalado", escalamientos=[e.categoria for e in escalamientos])

        clave = clave_del_recuerdo(pregunta)
        if clave:
            ev("recuerdo", dato=clave, sabido=bool(sesion is not None and sesion.datos.get(clave)))
            return Respuesta(responder_recuerdo(sesion.datos if sesion is not None else None, clave), "respondido",
                             conversacional=True)
        if es_saludo(pregunta):
            ev("saludo")
            return Respuesta(MENSAJE_SALUDO, "respondido")
        if es_despedida(pregunta):
            ev("despedida")
            return Respuesta(MENSAJE_DESPEDIDA, "respondido")
        if es_agradecimiento(pregunta):
            ev("agradecimiento")
            return Respuesta(MENSAJE_AGRADECIMIENTO, "respondido")
        if repreguntar and dice_sin_comprobante(pregunta):
            ev("sin_comprobante")
            return self._sin_comprobante(pregunta, sesion)

        return self._responder(pregunta, ev, con_respaldo=True, sesion=sesion, lugar_dado=lugar_dado,
                               repreguntar=repreguntar)

    def _respuesta_de_plazo(self, dias: int, fuentes: list[str], pregunta: str, producto: str | None = None) -> str:
        """El plazo de devolución según los días y, si corresponde, la garantía. `producto` es el del pedido del cliente."""
        texto = f"{nota_de_devolucion(dias)} [devoluciones]"
        # Pasados los 30 días solo cuenta la garantía, y si la pregunta la nombra ("devolverlo o usar la garantía") se responde
        # también dentro de los 30. Con el producto y el tiempo se hace la cuenta; con el producto solo, se dice cuánto dura; si
        # no, se da el documento (siempre que la garantía venga al caso por la pregunta o por los documentos recuperados).
        despues_de_30 = dias > PLAZO_DEVOLUCION_DIAS
        pregunta_por_la_garantia = "garantia" in fuentes and "garant" in guardrails.normalizar(pregunta)
        if despues_de_30 or pregunta_por_la_garantia:
            propia = (garantia_del_producto(pregunta, devolucion=despues_de_30, requiere_motivo=False, producto=producto)
                      or (garantia_de(producto) if producto else None))
            garantia = next((f for f in getattr(self.indice, "indice", self.indice).fragmentos if f.documento == "garantia"), None)
            if propia is not None:
                texto += f"\n\n{propia} [garantia]"
            elif garantia is not None and "garantia" in fuentes:
                cuerpo = re.sub(r"^#.*\n+", "", garantia.texto).strip()
                texto += f"\n\n{para_el_cliente(cuerpo)} [garantia]"
        return texto

    def _sin_comprobante(self, pregunta: str, sesion: Sesion | None) -> Respuesta:
        """No le dieron la factura o el comprobante de compra: los documentos no dicen qué hacer, y no se inventa. Se
        responde eso, se da lo que sí dice la garantía si preguntó por ella y se pregunta si quiere hacer un reclamo (si
        dice que sí, se deriva a una persona)."""
        partes: list[str] = []
        fuentes: list[str] = []
        if "garantia" in guardrails.normalizar(pregunta):
            garantia = next((f for f in getattr(self.indice, "indice", self.indice).fragmentos if f.documento == "garantia"), None)
            if garantia is not None:
                cuerpo = re.sub(r"^#.*\n+", "", garantia.texto).strip()
                partes.append(f"{para_el_cliente(cuerpo)} [garantia]")
                fuentes.append("garantia")
        if PIDE_COPIA.search(guardrails.normalizar(pregunta)):
            partes.append("Mis documentos no dicen cómo pedir una copia de la factura o del comprobante de compra. " + PREGUNTA_RECLAMO)
        else:
            partes.append("Mis documentos no dicen qué hacer cuando no se recibe la factura o el comprobante de compra. "
                          + PREGUNTA_RECLAMO)
        if sesion is not None:
            sesion.esperar("reclamo", pregunta)
        return Respuesta("\n\n".join(partes), "respondido", fuentes)

    def _responder_parte_permitida(self, pregunta: str, ev: Callable[..., None], derivadas: list[str] | None = None
                                   ) -> tuple[str, list[str], list[dict[str, Any]]] | None:
        """En una pregunta mixta responde las cláusulas que no hay que derivar (por ejemplo la garantía o el
        estado de un pedido). Devuelve None si no hay nada que responder con los documentos o la tool."""
        clausulas = segmentar(pregunta)[1:]
        with etapa("guardrail"):
            permitidas = [c for c in clausulas if tokenizar(c) and not guardrails.evaluar(c, self.clasificador)]
        if "reembolso_mayor_500" in (derivadas or []):
            # ya se deriva el reembolso: repetir la política de reembolsos de otra cláusula que también lo pide confunde
            permitidas = [c for c in permitidas if not (pide_reembolso(c) or (
                "reembols" in guardrails.normalizar(c) and guardrails.extraer_montos(c)))]
        if not permitidas:
            return None
        ev("parte_permitida", clausulas=len(permitidas))      # solo la cantidad: la traza no guarda texto del cliente
        r = self._responder(". ".join(permitidas), ev, con_respaldo=False, excluir={"contacto"}, derivando=True)
        return None if r is None else (r.texto, r.fuentes, r.pedidos)

    def _responder(self, pregunta: str, ev: Callable[..., None], con_respaldo: bool,
                   excluir: set[str] | None = None, sesion: Sesion | None = None, lugar_dado=None,
                   repreguntar: bool = True, derivando: bool = False) -> Respuesta | None:
        """RAG y tool de pedidos sobre `pregunta` y redacción. Sin `con_respaldo`, devuelve None cuando no hay
        nada relevante en lugar de un mensaje de 'no sé' (para la parte permitida de una pregunta mixta)."""
        pedidos = []
        with etapa("pedidos"):
            for id_pedido, literal in extraer_referencias(pregunta):
                p = consultar_estado_pedido(id_pedido)
                if re.sub(r"\s+", "", literal.upper()) != id_pedido:
                    p["entendido_como"] = literal      # no escribió ORD-XXXX: se le muestra qué se entendió
                pedidos.append(p)
                ev("tool", nombre="consultar_estado_pedido", order_id=p["order_id"], encontrado=p["encontrado"])
            for literal in extraer_identificadores_raros(pregunta):
                p = consultar_estado_pedido(literal)           # no es un ORD-XXXX: la tool dice que no lo encuentra
                p["formato_invalido"] = True
                pedidos.append(p)
                # el texto del cliente no va a la traza: lo que sigue a "pedido" o "código" puede ser cualquier dato (una tarjeta, un DNI)
                ev("tool", nombre="consultar_estado_pedido", encontrado=False, formato_invalido=True, largo=len(literal))
        with etapa("intencion"):
            consulta_sin_numero = not pedidos and self._consulta_de_pedido(pregunta)
        if consulta_sin_numero:
            ev("intencion", categoria="consulta_pedido_sin_numero")
            if sesion is not None and repreguntar:
                sesion.esperar("pedido", pregunta)

        with etapa("recuperacion"):
            resultados = [r for r in self.indice.buscar(pregunta) if r.fragmento.documento not in (excluir or set())]
        if TIEMPO.search(guardrails.normalizar(pregunta)) and not tokenizar(re.sub(r"\bhace\b", " ", TIEMPO.sub(" ", guardrails.normalizar(pregunta)))):
            resultados = []                       # "hace 10 días" solo: "días" no lo vuelve una pregunta de reembolsos
        ev("rag", fuentes=[r.fragmento.documento for r in resultados],
           puntajes=[round(r.puntaje, 2) for r in resultados], coberturas=[round(r.cobertura, 2) for r in resultados])
        # "Soy de Lima, cuánto tarda?": nombra un lugar y pregunta por un plazo, es de envíos aunque no diga la palabra
        seguimiento = bool(re.match(r"y (?:a|en|para|hasta) ", guardrails.normalizar(pregunta).strip(" ¿?")))     # "y a Mendoza?"
        if (not resultados and not pedidos and resolver_lugares(pregunta) and "envios" not in (excluir or ())
                and (INTENCION_ENVIO.search(guardrails.normalizar(pregunta)) or seguimiento)):
            envios = next((f for f in getattr(self.indice, "indice", self.indice).fragmentos if f.documento == "envios"), None)
            if envios is not None:
                resultados = [ResultadoRAG(envios, 1.0, 1.0)]
        # El documento de envíos solo corresponde si la pregunta habla de un envío: nombrar un lugar ("capital de
        # Francia") no alcanza, y sin esta revisión una pregunta de geografía recibiría una respuesta de envíos.
        if (any(r.fragmento.documento == "envios" for r in resultados)
                and not INTENCION_ENVIO.search(guardrails.normalizar(pregunta)) and not seguimiento and resolver_lugares(pregunta)):
            resultados = [r for r in resultados if r.fragmento.documento != "envios"]
        # "Cuánto tarda en llegar el reembolso?" habla del reembolso: "llega" y "tarda" solos no son una pregunta de envío
        if (any(r.fragmento.documento == "envios" for r in resultados)
                and any(r.fragmento.documento in ("reembolsos", "devoluciones", "garantia") for r in resultados)
                and not ENVIO_EXPLICITO.search(guardrails.normalizar(pregunta))):
            resultados = [r for r in resultados if r.fragmento.documento != "envios"]
        if guardrails.NIEGA_REEMBOLSO.search(guardrails.normalizar(pregunta)):
            # "No quiero un reembolso, solo saber la garantía": lo que niega no se responde, solo lo que sí pregunta
            resto = guardrails.NIEGA_REEMBOLSO.sub(" ", guardrails.normalizar(pregunta))
            resultados = [r for r in resultados if r.fragmento.documento not in ("reembolsos", "devoluciones")
                          or NOMBRA_EL_DOCUMENTO[r.fragmento.documento].search(resto)]
        # con el pedido en mano, el estado ya responde "dónde está": el plazo general de envío sobra si no nombra un lugar
        if pedidos and not resolver_lugares(pregunta):
            resultados = [r for r in resultados if r.fragmento.documento != "envios"]
        # "Mi garantía vence en 2 días" es de garantía: el plazo de devolución solo corresponde si habla de devolver o cambiar
        if ("garant" in guardrails.normalizar(pregunta) and not re.search("devol|devuelv|cambi|reembols|arrepent|regres", guardrails.normalizar(pregunta))):
            resultados = [r for r in resultados if r.fragmento.documento != "devoluciones"]
        # "Quiero hacer una devolución" no habla de plata: el documento de reembolsos solo sobra cuando no se la nombra
        norm_p = guardrails.normalizar(pregunta)
        if (any(r.fragmento.documento == "devoluciones" for r in resultados)
                and not HABLA_DE_PLATA.search(norm_p) and "reembolsos" not in (excluir or ())):
            resultados = [r for r in resultados if r.fragmento.documento != "reembolsos"]
        # el pedido es de algo que el agente no hace: solo se muestran los documentos que la pregunta nombra
        accion = bool(ACCION_QUE_NO_PUEDE.search(guardrails.normalizar(pregunta)))
        if accion:
            resultados = [r for r in resultados if NOMBRA_EL_DOCUMENTO[r.fragmento.documento].search(guardrails.normalizar(pregunta))]
        # "Mi pedido llegó fallado, puedo devolverlo o usar la garantía?": si la pregunta nombra la garantía, también se responde esa mitad
        if (pedidos and QUIERE_DEVOLVER.search(norm_p) and "garant" in norm_p
                and not any(r.fragmento.documento == "garantia" for r in resultados)):
            garantia_doc = next((f for f in getattr(self.indice, "indice", self.indice).fragmentos if f.documento == "garantia"), None)
            if garantia_doc is not None:
                resultados.append(ResultadoRAG(garantia_doc, 1.0, 1.0))
        fuentes = [r.fragmento.documento for r in resultados]

        notas = notas_obligatorias(pregunta, fuentes, consulta_sin_numero, derivando)
        if accion:
            notas.append(MENSAJE_SIN_ACCIONES)          # pide algo que el agente no hace: se aclara, no se finge
        if repreguntar and "reembolsos" in fuentes and pide_reembolso(pregunta) and not guardrails.extraer_montos(pregunta):
            # Quiere un reembolso y no dijo el monto: de eso depende la respuesta, así que se pregunta en vez de volcar la
            # política. Si la pregunta toca otros temas, la pregunta se agrega al final de lo que se responde.
            if sesion is not None:
                sesion.esperar("monto", pregunta)
            if not pedidos and set(fuentes) <= {"reembolsos", "devoluciones"}:
                return Respuesta(PREGUNTA_MONTO, "respondido", ["reembolsos"])
            notas.append(PREGUNTA_MONTO)
        elif repreguntar and not pedidos and not consulta_sin_numero and pregunta_por_su_compra(pregunta, fuentes):
            # Quiere devolver o usar la garantía de algo y no dice cuándo lo compró: de eso depende la respuesta
            if sesion is not None:
                sesion.esperar("antiguedad", pregunta)
            return Respuesta(PREGUNTA_ANTIGUEDAD, "respondido", fuentes)
        if "devoluciones" in fuentes and QUIERE_DEVOLVER.search(guardrails.normalizar(pregunta)):
            for p in pedidos:                       # con el pedido en mano: qué dice el estado y, si falta, hace cuánto compró
                if not p["encontrado"]:
                    continue
                if p["estado"] == "Entregado":
                    if not TIEMPO.search(guardrails.normalizar(pregunta)) and repreguntar:
                        notas.append(PREGUNTA_FECHA_COMPRA)
                        if sesion is not None:
                            sesion.esperar("antiguedad", pregunta)
                elif p["estado"] == "Cancelado":
                    notas.append(f"El pedido {p['order_id']} figura como cancelado: no hay un producto entregado para devolver.")
                else:
                    notas.append(f"El pedido {p['order_id']} todavía no figura como entregado.")
        # Devolver algo que compró hace tantos días: es una cuenta del Doc 2, no una opinión. Se responde por código (un modelo
        # chico a veces decía "no se acepta después de 30 días si no fue usado", y a veces lo contrario).
        # Con un pedido entregado el producto sale del pedido y la respuesta empieza por su estado.
        dias = dias_desde_la_compra(pregunta) if "devoluciones" in fuentes else None
        entregados = bool(pedidos) and all(p["encontrado"] and p["estado"] == "Entregado" for p in pedidos)
        if (dias is not None and (not pedidos or entregados) and set(fuentes) <= {"devoluciones", "garantia"}
                and not NO_DEVOLVIBLE.search(guardrails.normalizar(pregunta))):
            ev("plazo_de_devolucion", dias=dias)
            producto = pedidos[0]["producto"] if len(pedidos) == 1 else None
            plazo = self._respuesta_de_plazo(dias, fuentes, pregunta, producto)
            estado = redactar_offline([], pedidos, [], None) if pedidos else ""
            citadas = fuentes + (["garantia"] if "[garantia]" in plazo and "garantia" not in fuentes else [])
            return Respuesta(f"{estado}\n\n{plazo}" if estado else plazo, "respondido", citadas, pedidos=pedidos)
        # Garantía de algo que tiene hace tantos meses: también es una cuenta del Doc 1 (12 meses los grandes, 6 los pequeños)
        garantia = respuesta_de_garantia(pregunta) if fuentes == ["garantia"] and not pedidos else None
        if garantia:
            ev("plazo_de_garantia")
            return Respuesta(f"{garantia} [garantia]", "respondido", fuentes)
        # "Con quién hablo...?": el único canal humano que figura en los documentos es el del Doc 5. Se responde con
        # una frase fija y no con el modelo, que a veces la completaba con un motivo inventado ("quejas sobre reembolsos").
        p_norm = guardrails.normalizar(pregunta)
        canal = not excluir and bool(guardrails._es_consulta_de_canal(p_norm) or _PIDE_CANAL.search(p_norm))
        if canal and "contacto" not in fuentes:
            fuentes.append("contacto")
        if canal and not resultados and not pedidos:
            return Respuesta(TEXTO_CANAL, "respondido", ["contacto"])
        if accion and not resultados and not pedidos:
            return Respuesta(MENSAJE_SIN_ACCIONES, "respondido")
        if not resultados and not pedidos:
            if not con_respaldo:
                return None
            if consulta_sin_numero:
                return Respuesta(pedir_numero(pregunta), "respondido")
            return Respuesta(MENSAJE_SIN_INFO, "sin_informacion")

        # El plazo de envío según el lugar lo resuelve el código (lugares.py): el modelo no tiene que adivinar cuál es la
        # capital. Esa parte se saca de lo que redacta el modelo y se agrega ya resuelta.
        envio = None
        if "envios" in fuentes and not resolver_lugares(pregunta) and INTERNACIONAL.search(guardrails.normalizar(pregunta)):
            envio = "Los envíos internacionales no están disponibles actualmente. [envios]"     # lo que pregunta, sin pedir la ciudad
        elif "envios" in fuentes:
            lugares = [lugar_dado] if lugar_dado else resolver_lugares(pregunta)
            if lugares:
                por_confirmar = confirmacion(lugares)      # lugar ambiguo o desconocido: se le pregunta
                if por_confirmar and not repreguntar:
                    envio = respuesta_envio_sin_lugar(preguntar=False)
                else:
                    envio = respuesta_envio(lugares)
                    if por_confirmar and sesion is not None:
                        sesion.esperar("lugar_confirmar", pregunta, *por_confirmar)
            elif fuentes == ["envios"] and not pedidos and not consulta_sin_numero:
                envio = respuesta_envio_sin_lugar(preguntar=repreguntar)
                if repreguntar and sesion is not None:
                    sesion.esperar("lugar", pregunta)
            if envio and PIDE_COSTO.search(guardrails.normalizar(pregunta)):
                envio = f"{AVISO_SIN_COSTO} {envio}"      # los documentos no dicen cuánto cuesta enviar: no se inventa
            if envio:
                ev("envio", lugares=[(l.tipo) for l in lugares])
        redactables = [r for r in resultados if not (envio and r.fragmento.documento == "envios")
                       and not (canal and r.fragmento.documento == "contacto")]
        if canal:
            envio = f"{envio}\n\n{TEXTO_CANAL}" if envio else TEXTO_CANAL
        fuentes_red = [r.fragmento.documento for r in redactables]

        # Con un pedido en una consulta de devolución o garantía, el estado, los plazos y la garantía del producto los resuelve el
        # código. El modelo contestaba solo la mitad ("puedes usar la garantía") y la citaba mal, y el código daba por cubierta la
        # devolución por la cita.
        por_codigo = bool(pedidos) and bool(QUIERE_DEVOLVER.search(norm_p)) and set(fuentes) <= {"devoluciones", "garantia"}
        if por_codigo and len(pedidos) == 1 and pedidos[0]["encontrado"] and any(r.fragmento.documento == "garantia" for r in redactables):
            propia = garantia_de(pedidos[0]["producto"])
            if propia:
                redactables = [r for r in redactables if r.fragmento.documento != "garantia"]
                notas.insert(0, f"{propia} [garantia]")

        texto = None
        if self.llm is not None and redactables and not por_codigo:
            try:
                prompt = armar_prompt(self._sin_pedidos_ajenos(pregunta, ev), redactables, pedidos)
                with etapa("generacion"):
                    texto = self.llm.generar(SISTEMA, prompt)
                with etapa("validacion"):
                    texto = limpiar_citas(texto, fuentes_red)
                    problema = problema_de_salida(texto, prompt)
                if problema:
                    ev("llm", ok=False, error=problema)
                    texto = None
                else:
                    ev("llm", ok=True)
                    # Cobertura: si la pregunta toca dos políticas (por ejemplo garantía y devolución) y el modelo
                    # solo citó una, se agrega el texto de la otra. No depende de que el modelo se acuerde.
                    texto, agregados = completar_cobertura(texto, redactables, pregunta)
                    if agregados:
                        ev("cobertura", agregados=agregados)
                    if envio:
                        texto = texto + "\n\n" + envio
                    # Las aclaraciones obligatorias (regla de los $500, pedir el número) las agrega el código: un
                    # modelo chico las omite a veces, y no pueden depender de que el modelo las copie.
                    if notas:
                        texto = texto + "\n\n" + "\n".join(notas)
            except Exception as e:          # un modelo que falla de cualquier forma no tumba la respuesta: sigue el modo offline
                ev("llm", ok=False, error=str(e) if isinstance(e, ErrorLLM) else f"{type(e).__name__}: {e}")
        if not texto:
            texto = redactar_offline(redactables, pedidos, notas, envio)
        return Respuesta(texto, "respondido", fuentes, pedidos=pedidos)

    def _sin_pedidos_ajenos(self, pregunta: str, ev: Callable[..., None]) -> str:
        """En una pregunta con varias cláusulas, saca las que piden una tarea ajena a la tienda ("escribime un poema",
        "contame un chiste") antes de dárselas al modelo: un modelo chico las obedece aunque se le diga que no. Una
        cláusula se saca solo si pide algo (verbo de tarea) y ningún documento ni pedido se relaciona con ella."""
        clausulas = segmentar(pregunta)[1:]
        if len(clausulas) < 2:
            return pregunta
        propias = [c for c in clausulas
                   if not TAREA_AJENA.search(guardrails.normalizar(c)) or extraer_referencias(c) or self.indice.buscar(c)]
        if not propias or len(propias) == len(clausulas):
            return pregunta
        ev("pedido_ajeno_descartado", clausulas=len(clausulas) - len(propias))
        return ". ".join(propias)

    def _consulta_de_pedido(self, pregunta: str) -> bool:
        """¿Pregunta por el estado de un pedido? Por significado (embeddings o n-gramas), o por palabras clave
        como último recurso."""
        p = re.sub(r"\bmi (casa|domicilio|direccion|ciudad|zona|barrio|provincia|pais)\b", " ", guardrails.normalizar(pregunta))     # "a mi casa" no es "mi pedido"
        if COMPRA_FUTURA.search(p):          # "voy a comprar...", "si compro mañana...": todavía no hay pedido
            return False
        if TEMA_DE_POLITICA.search(p) and not TEMA_DE_ESTADO.search(p):
            return False                      # habla de devolver, de la garantía o de una falla, no del estado de un envío
        # Por significado, y solo si habla de algo propio ("mi pedido", "compré", "hice un pedido"): "cuánto tarda el
        # envío?" a secas es una pregunta de política, no el estado de un pedido.
        if COMPRA_PROPIA.search(p) and OBJETO_DE_COMPRA.search(p) and INTENCIONES[0] in self.clasificador.detectar(pregunta, INTENCIONES):
            return True
        if re.search(r"\bestado (?:de|del) (?:mi |el |la |un |una |tu )?(?:pedido|orden|compra|envio|paquete)s?\b", p):
            return True
        return bool(re.search(r"\b(mi|mis)\s+(pedido|orden|compra|adquisicion|encargo|envio)s?\b|lo que (compre|pedi|encargue)", p)
                    and re.search(r"estado|donde|rastre|llega|seguimiento|cuando|demora|info|detalle", p))

    def _guardar(self, traza: list[dict[str, Any]]) -> None:
        texto = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in traza)
        with _CANDADO_TRAZAS:                       # varias respuestas a la vez no mezclan sus líneas
            self.trazas_dir.mkdir(parents=True, exist_ok=True)
            with (self.trazas_dir / "trazas.jsonl").open("a", encoding="utf-8") as f:
                f.write(texto)
