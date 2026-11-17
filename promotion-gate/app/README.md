# App del gate de promoción (Fabric App con Rayfin)

La cara del gate para el equipo de desarrollo: elegir el modelo semántico y su informe, preparar el escenario de carga,
lanzar `PL_PromotionGate`, seguir sus fases en vivo, leer el veredicto con toda su evidencia y firmar la promoción a
producción con el deployment pipeline. El motor sigue siendo el de `../` (notebooks, pipeline y paquete
`promotion_gate`); la app no calcula nada, solo prepara, lanza, sigue y presenta.

| Vista | Qué hace |
|---|---|
| Nuevo gate | Bloques 1 a 4: workspace, modelo e informe; escenario (subir la grabación de Performance Analyzer, reutilizar una ya subida o generar una sintética desde las medidas del modelo); rampa, usuarios objetivo y SKU; plan de fases con tiempo estimado y «Lanzar gate» |
| Run | Número de certificado, ruta de cinco fases con los niveles de la rampa en vivo, etiqueta de veredicto (apto, con observaciones o no apto) y pestañas: comprobaciones, mejoras priorizadas, test de carga (gráfico p50 y p95 frente al SLO, niveles, visuales y DAX lentos), buenas prácticas (BPA y VertiPaq) y Capacity Metrics |
| Firma | Busca la ruta del deployment pipeline (stage del workspace y el siguiente) y despliega modelo e informe tras escribir el nombre del modelo; queda sellado como «Promocionado» |
| Runs | Historial del equipo con filtros y orden |
| Ajustes | Conexión, umbrales de `gate.yaml` (solo lectura) y permisos que pide la app |

## Arquitectura

```text
Navegador (Fabric App, iframe del portal o pestaña propia)
├─ Rayfin: SSO de Fabric + SQL DB/GraphQL de la app → entidad GateRun (historial del equipo)
└─ MSAL (SPA, token delegado del usuario, consentimiento incremental)
   ├─ api.fabric.microsoft.com   workspaces, modelos, jobs de PL_PromotionGate, queryactivityruns, deployment pipelines
   ├─ api.powerbi.com            informes del modelo, executeQueries (INFO.VIEW) para el escenario sintético
   └─ onelake.dfs.fabric...      subir escenarios, leer gate.yaml, evidencias y summary.json de cada nivel
```

Las tres APIs aceptan CORS desde el origen de una Fabric App (comprobado el 2026-11-05). Fabric no expone la cabecera
`Location` por CORS, así que la app genera el `run_id`, lo pasa al pipeline y localiza el job buscando ese `run_id` en
la entrada de sus actividades; para los despliegues consulta la lista de operaciones del deployment pipeline.

La app solo ajusta por run los usuarios objetivo y el SKU (`gate_config`); los SLO del equipo se quedan en `gate.yaml`.

## Requisitos, despliegue y modos locales

Todo está en el [README del gate](../README.md): `deploy/deploy.ps1` crea el registro SPA de Entra, escribe `.env` y
ejecuta `rayfin up`; `npm run dev:demo` funciona sin Azure y `npm run dev` (`rayfin dev`) ejecuta la app en local contra
el backend desplegado en Fabric.

Scopes delegados que pide la app (consentimiento en el primer inicio de sesión): Fabric (`Workspace.Read.All`,
`Item.Read.All`, `Item.Execute.All`, `Pipeline.Read.All`, `Pipeline.Deploy`), Power BI (`Report.Read.All`,
`Dataset.Read.All`) y Azure Storage (`user_impersonation`, para OneLake).

Dentro del portal, la app vive en un iframe con almacenamiento particionado: el login va por `popup-relay.html`
(relay de MSAL) y vuelve por `blank.html` (`broadcastResponseToMainFrame`).

## Validación

```powershell
npm run typecheck     # app y entidades Rayfin
npm test              # vitest: parámetros contra PL_PromotionGate.json, fases, localización del job, ruta de promoción, escenarios
npm run build
```

El escenario sintético se ha comprobado contra `load_queries` del orquestador real (`RunPerfScenario_v3`): 8 consultas,
2 acciones y la pausa grabada reproducida como think time.

## Diseño

Mundo visual: certificado de aptitud para el servicio (EASA Form 1) y etiquetas de estado colgantes. Contexto de
producto en `PRODUCT.md`, sistema visual en `DESIGN.md` y contrato de la superficie en `.impeccable/surfaces/`.
