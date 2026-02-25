# Skill: OpenClaw Memory Bootstrap

## Objetivo

Configurar este agente como un agente OpenClaw con memoria compartida en Supabase.
Al finalizar, el agente tendrá identidad propia, podrá almacenar y recuperar memorias,
y tendrá acceso a las bases de conocimiento RAG existentes.

## Pre-requisitos

Necesitas estas variables de entorno configuradas en `.env`:

```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...  (service_role key)
OLLAMA_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
```

Si `.env` no existe o le faltan valores, **detente y pide las credenciales al usuario**.

## Pasos

Ejecuta estos pasos EN ORDEN. Si alguno falla, no continúes — reporta el error.

### Paso 1: Validar entorno

Ejecuta `bootstrap.py validate` desde este directorio.
Verifica que:
- `.env` existe y tiene SUPABASE_URL y SUPABASE_KEY no vacíos
- Supabase responde (HTTP 200 en `/rest/v1/`)
- Ollama responde y tiene el modelo de embeddings disponible

Si la validación falla, muestra qué falta y pide al usuario que lo configure.

### Paso 2: Aplicar schema

Ejecuta `bootstrap.py schema` desde este directorio.
Esto aplica `schema.sql` (tablas RAG base) y `schema_memory.sql` (tablas de memoria multi-agente).
Las tablas usan `IF NOT EXISTS`, así que es seguro re-ejecutar.

Verifica que el comando reporte éxito. Si falla con error de permisos,
el usuario necesita usar el **service_role key** (no el anon key).

### Paso 3: Registrar agente

Ejecuta `bootstrap.py register` desde este directorio.
Esto:
1. Genera un API key único (`oc_sk_...`)
2. Registra el agente en `mb_agents` con el nombre de `OPENCLAW_AGENT_NAME`
   (o genera un nombre automático si no está configurado)
3. Guarda el API key en `.env` como `OPENCLAW_AGENT_KEY`
4. Autentica al agente para verificar que el key funciona

**IMPORTANTE**: El API key se muestra UNA SOLA VEZ. Asegúrate de que quedó guardado en `.env`.

Si el agente ya está registrado (nombre duplicado), el script lo detecta y solo autentica.

### Paso 4: Bootstrap de acceso a RAG

Ejecuta `bootstrap.py access` desde este directorio.
Esto da acceso global al agente sobre todos los `kb_sources` existentes,
para que pueda buscar en las bases de conocimiento RAG ya cargadas.

### Paso 5: Test de humo

Ejecuta `bootstrap.py test` desde este directorio.
Esto ejecuta un flujo completo:
1. `remember()` — almacena una memoria de prueba
2. `recall()` — busca la memoria por similitud semántica
3. `recall_all()` — búsqueda unificada (memoria + RAG)
4. `forget()` — elimina la memoria de prueba

Cada paso debe reportar OK. Si alguno falla, reporta el error detallado.

### Paso 6: Resumen

Si todos los pasos pasaron, muestra al usuario:
- Nombre del agente
- ID del agente (UUID)
- Número de fuentes RAG accesibles
- Número de memorias almacenadas
- Confirmación de que el sistema está listo

## Ejecución rápida

Si quieres ejecutar todos los pasos de una vez:

```bash
python3 skills/bootstrap/bootstrap.py all
```

## Troubleshooting

| Error | Causa probable | Solución |
|-------|---------------|----------|
| `Connection refused` en Supabase | URL incorrecta o proyecto pausado | Verificar SUPABASE_URL en dashboard |
| `401 Unauthorized` | Key inválido o expirado | Usar service_role key, no anon key |
| `Could not find function` en RPC | Schema no aplicado | Re-ejecutar paso 2 |
| `Connection refused` en Ollama | Ollama no está corriendo | `ollama serve` en otra terminal |
| `Model not found` | Modelo no descargado | `ollama pull nomic-embed-text` |
| `duplicate key value` en register | Agente ya existe | Normal — el script autentica en su lugar |
