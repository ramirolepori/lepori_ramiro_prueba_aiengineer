# Arquitectura del agente de soporte de TiendaHogar

Este documento describe cómo está armado el agente y cómo extenderlo. El porqué de cada decisión está en los [ADR](adr/README.md).

## Flujo de una pregunta

```
cliente ── pregunta ──► AgenteSoporte.responder(pregunta, sesion=None)
                          │
   1. entrada ──── vacía ─► pide la consulta; más de 2000 caracteres ─► se recorta
   2. detectar_inyeccion ── sí ─► rechazo, sin modelo
   3. sesión (si hay y hay un dato pendiente) ── el mensaje responde la repregunta ─► consulta completa
   4. guardrails.evaluar ── sí ─► derivación a soporte@tiendahogar.example, sin modelo
   │        (reglas + similitud por embeddings, o n-gramas si no hay embeddings)
   │        pregunta mixta: antes se responde la parte permitida
   5. pedidos ── ORD-XXXX, "pedido 1001", "n°2000"... ─► consultar_estado_pedido (tabla mock)
   6. recuperación ── embeddings + BM25, por consulta y por cláusula ─► documentos relevantes
   │        ningún documento ni pedido ─► "no tengo esa información" (o pide el número de pedido)
   7. envíos ── lugares.resolver_lugares ─► plazo por plantilla (capital, otras ciudades, exterior)
   8. redacción ── con modelo (solo el contexto recuperado) │ sin modelo: cita los documentos
   9. validación ── cifras o correos inventados ─► se descarta y se usa el modo offline
   │        cobertura de las políticas, notas obligatorias y repreguntas, agregadas por código
  10. traza JSONL y tiempos por etapa ─► Respuesta
```

El orden importa: lo que el enunciado trata como regla (derivar, no inventar, no aprobar reembolsos) se resuelve en código antes o después del modelo, nunca dentro de él (ADR 0002).

## Módulos

Todo el código está en `src/tiendahogar/` y usa solo la librería estándar.

| Módulo | Responsabilidad |
| --- | --- |
| `agent.py` | El flujo de arriba: `AgenteSoporte`, `Respuesta`, preguntas mixtas, validación de la salida, cobertura y notas |
| `guardrails.py` | Reglas de escalamiento (reembolso de más de $500, trato, facturación, legal), preguntas por el canal, inyección |
| `semantica.py` | Clasificación por significado: embeddings y n-gramas, evaluación por oración, categorías y anclas |
| `montos.py` | Extracción de montos en distintos formatos (`$1.000`, `2k`, `2 lucas`, `mil quinientos`, `USD600`) |
| `rag.py` | Fragmentación, BM25 con conceptos, recuperador híbrido y umbral por margen |
| `embeddings.py` | Cliente de `/v1/embeddings`, vectores unitarios, caché en disco de los textos fijos |
| `pedidos.py` | `consultar_estado_pedido`, tabla mock y extracción flexible de números e identificadores raros |
| `lugares.py` | Gazetteer y reglas para el plazo de envío según el lugar (`data/lugares.json`) |
| `sesion.py` | Memoria de la conversación: dato pendiente, repreguntas y cómo se lee la respuesta |
| `llm.py` | Clientes OpenAI-compatible y Anthropic con `urllib`, corte de circuito y respaldo |
| `config.py` | Variables de entorno |
| `evaluacion.py`, `independiente.py` | Medición del guardrail, los pedidos y el RAG, y de los lotes de frases ajenas |
| `rendimiento.py`, `tiempos.py` | Latencia por etapa y por balde (modelo de lenguaje, embeddings, código propio) |

Datos en `src/tiendahogar/data/`: `docs/` (los 5 documentos del enunciado, sin editar), `anclas.json` (frases de ejemplo por categoría del guardrail y de la consulta de pedidos), `fuera_de_alcance.json` (preguntas que los documentos no responden, referencia del umbral del RAG) y `lugares.json` (gazetteer de envíos). Datos de evaluación en `tests/data/`.

## Contratos

`consultar_estado_pedido(order_id: str) -> dict`: devuelve `order_id`, `encontrado`, `producto`, `estado` y `entrega_estimada` si el pedido existe, y `encontrado: False`, `estado: "No encontrado"` y un mensaje si no existe. Nunca inventa datos.

`AgenteSoporte.responder(pregunta, sesion=None) -> Respuesta`. Sin `sesion`, cada pregunta es independiente, también si se reutiliza el agente. Con una `Sesion`, el agente recuerda qué dato le pidió al cliente (ADR 0008).

`Respuesta`: `texto`, `estado` (`respondido`, `escalado`, `sin_informacion` o `bloqueado`), `fuentes` (documentos citados), `escalamientos` (categorías del guardrail), `pedidos`, `traza` (eventos de cada paso) y `tiempos` (milisegundos por etapa y por balde).

La traza (`trazas/trazas.jsonl` si se configura `trazas_dir`, ignorada por git) guarda el largo de la consulta, las categorías y el origen de cada derivación (regla o semántica), los documentos recuperados con sus puntajes, los pedidos consultados, si el modelo respondió o se descartó su respuesta y los tiempos. No guarda el texto de la consulta ni de la respuesta.

## Cómo extender el agente

- Un documento nuevo: agregar el `.md` a `data/docs/`. El recuperador lo indexa solo. Revisar `data/fuera_de_alcance.json` y la tabla `CONCEPTOS` de `rag.py` si tiene sinónimos propios, y medir con `python -m tiendahogar.evaluacion rag`.
- Una categoría de derivación: sumar las reglas en `guardrails.py`, las frases de ejemplo en `data/anclas.json` y la palabra del tema en `_TEMA`, agregar casos a `tests/data/guardrail_evaluacion.json` y medir con `python -m tiendahogar.evaluacion`.
- Un lugar de envío: agregarlo a `data/lugares.json` (el formato está en el campo `_nota`).
- Un dato que el agente repregunte: definir el dato pendiente y cómo se lee la respuesta en `sesion.py` y dónde se pregunta en `agent.py`, con tests de conversación en `tests/test_sesion.py`.
- Un proveedor de modelos: es compatible con la API de OpenAI si basta cambiar `LLM_BASE_URL`; si no, un cliente nuevo en `llm.py` con la misma interfaz (`generar(sistema, prompt)`).

## Reglas que no se rompen

- Los 5 documentos del enunciado se usan tal cual, sin editarlos.
- El guardrail y la tool corren en código, antes del modelo. El modelo no clasifica ni decide el flujo.
- El agente no inventa: ni datos de pedidos, ni plazos, ni montos. Un identificador raro no se corrige en silencio.
- No confirma ni promete que un reembolso o una devolución fue aprobado o ejecutado.
- Lo que no tiene que ver con los documentos no llega al modelo: sin un documento ni un pedido relevante se responde que no hay información (ADR 0011).
- La memoria es opcional y nunca saltea el guardrail.
- Sin claves en el repositorio y sin texto del cliente en las trazas.
- Después de un cambio, correr `python -m pytest tests/` y las mediciones de `SUBMISSION.md`. Un lote de frases ajenas se mide una vez antes de corregir.
