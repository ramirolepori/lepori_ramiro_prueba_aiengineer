"""Textos fijos que el agente le dice al cliente. Ninguno depende del modelo."""

from . import guardrails

MENSAJE_VACIO = "No recibí ninguna consulta. Contame en qué te puedo ayudar: garantías, devoluciones, envíos, reembolsos o el estado de un pedido."
MENSAJE_BLOQUEO = "No puedo procesar ese pedido porque intenta cambiar mis reglas de funcionamiento."
MENSAJE_SIN_ACCIONES = ("No puedo realizar esa acción (enviar correos o mensajes, reservar, comprar, cancelar o modificar un pedido o "
                        "generar comprobantes): solo puedo informarte sobre garantías, devoluciones, envíos, reembolsos y el estado "
                        f"de un pedido. Si necesitás que lo gestione una persona, escribí a {guardrails.CONTACTO}.")
TEXTO_CANAL = (f"Para hablar con una persona, escribí a {guardrails.CONTACTO}. Es el canal de atención humana para quejas "
               f"sobre el trato de un empleado, disputas de facturación y temas legales. [contacto]")
MENSAJE_SIN_INFO = (
    "No tengo esa información en nuestras políticas. Puedo ayudarte con garantías, devoluciones, tiempos de envío, "
    "reembolsos y el estado de un pedido (con su número ORD-XXXX)."
)
MENSAJE_AGRADECIMIENTO = ("¡Gracias por tu mensaje! Me alegra que haya salido todo bien. Si necesitás algo más, puedo ayudarte "
                          "con garantías, devoluciones, tiempos de envío, reembolsos y el estado de un pedido.")
MENSAJE_SALUDO = ("¡Hola! Soy el asistente de soporte de TiendaHogar. Puedo ayudarte con garantías, devoluciones, tiempos de "
                  "envío, reembolsos y el estado de un pedido (con su número ORD-XXXX). ¿En qué te ayudo?")
MENSAJE_DESPEDIDA = "¡Chau! Que tengas un buen día. Si necesitás algo más, acá estoy."
PREGUNTA_FECHA_COMPRA = "¿Hace cuánto lo compraste? Con eso te digo si todavía estás dentro de los 30 días."
AVISO_SIN_COSTO = "Los documentos no indican el costo del envío."
