---
name: model-bpa-review
description: >-
  Revisión de buenas prácticas de un modelo semántico antes de promocionarlo: Best Practice Analyzer de
  semantic-link-labs, tamaño en memoria y columnas pesadas (VertiPaq) frente al límite del SKU. Úsala para
  «revisa las buenas prácticas del modelo», «pasa el BPA», «¿por qué falla la revisión del gate?», «qué columnas
  pesan más» o para corregir los hallazgos antes de repetir el gate.
---

# Revisión de buenas prácticas (fase 1 del gate)

## Lanzar solo esta fase

```powershell
smgate run-item --workspace-id $env:GATE_WORKSPACE_ID --name NB_Gate_ModelReview --wait `
  --param run_id=<run_id> --param dataset="<modelo>" --param model_workspace="<workspace>"
smgate fetch --workspace-id $env:GATE_WORKSPACE_ID --lakehouse-id $env:GATE_LAKEHOUSE_ID --run-id <run_id> --out out/<modelo>
```

Usa un `run_id` nuevo para una revisión suelta, o el del gate si quieres rehacer su evidencia antes del veredicto.

## Qué decide

| Comprobación | Regla por defecto | Efecto |
|---|---|---|
| `bpa_errors` | 0 violaciones de severidad Error | FAIL |
| `blocking_rules` | Reglas que el equipo declara bloqueantes en `config/gate.yaml` | FAIL |
| `bpa_warnings` | Más de 30 Warning | WARN |
| `memory` | Más del 50 % de la memoria máxima por modelo del SKU de producción | WARN |
| `heavy_columns` | Una columna por encima del 20 % del modelo | WARN |

Los nombres de regla son los de semantic-link-labs (`sempy_labs._model_bpa_rules`), por ejemplo
«Do not use floating point data types» o «Check if bi-directional and many-to-many relationships are valid».

## Cómo leer los hallazgos

1. Agrupa por regla, no por objeto: una regla con 40 columnas es una sola corrección de patrón.
2. Prioriza: Error, después Warning de la categoría Performance, después el resto. Info casi nunca bloquea.
3. Columnas pesadas: un GUID o clave de texto, una fecha con hora o un Double de alta cardinalidad son los
   culpables habituales. Proponer: quitar si no se usa, entero sustituto, separar fecha y hora, reducir decimales.
4. Memoria: el refresco completo de un modelo Import necesita aproximadamente el doble de su tamaño.

## Corregir

- Si el equipo trabaja con PBIP o TMDL en Git, propone el cambio en los ficheros y que lo suban por PR a dev.
- Con un modelo vivo en dev puedes usar `powerbi-modeling-mcp` o el agente `pbi-modelo` para aplicar el cambio,
  siempre con OK explícito y nunca en el stage de producción.
- Una excepción aceptada va a `model_review.ignored_rules` por PR, con el motivo en la descripción; el informe la lista.
