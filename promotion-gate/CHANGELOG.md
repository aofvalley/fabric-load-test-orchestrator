# Changelog del gate de promoción

El gate se versiona aparte del Fabric Load Test Orchestrator (`pyproject.toml`).

## Sin publicar

- App en el portal de Fabric: el primer inicio de sesión ya no falla con `timed_out`. La ventana de login se abre fuera
  del iframe y, la primera vez, pasa por el intersticial «Sign in required» del hosting protegido de Rayfin antes de
  «Continuar» y la cuenta de Microsoft; con la espera por defecto de MSAL (60 s) no daba tiempo. La app espera ahora
  hasta 5 minutos, como la propia página de relay, explica esos pasos junto al botón y muestra el error si falla.

## 0.1.0

Primera versión.

- Paquete `promotion_gate` y CLI `smgate`: BPA y VertiPaq, informe del test de carga con mejoras priorizadas, Capacity Metrics
  (FUAM v40 a v53, timepoints convertidos de la hora local de la app a UTC, operaciones por item en las horas del test) y
  veredicto PASS, WARN o FAIL.
- Notebooks `NB_Gate_*` (cargan el wheel por `sys.path`, válido en sesiones de alta concurrencia) y pipeline `PL_PromotionGate`.
- Requiere el orquestador 3.4.0 o posterior. Usuarios RLS por lista (`rls_users`) o por fichero (`rls_users_file`), traducidos a
  `rls_source` y `rls_scope = global` del orquestador.
- Fabric App con Rayfin: elegir modelo e informe, escenario (grabación, existente o sintético), lanzar, seguir, certificado y firma de
  la promoción con un deployment pipeline. Login dentro del iframe del portal con el relay de MSAL.
- `deploy/deploy.ps1` y `deploy/teardown.ps1`; caso de éxito Ventas Retail (Direct Lake que pasa el gate).
- Plugin para Copilot CLI y Claude Code; plantillas de CI para GitHub Actions y Azure DevOps.

Tras la revisión de #3:

- `smgate promote` y la firma de la app no se fían solo de `promotable`: debe cuadrar con `verdict` (PASS, o WARN con
  `warn_blocks_promotion: false`) y con el peor estado de las comprobaciones del `verdict.json`.
- Capacity Metrics: `capacity.json` y el informe dan el último timepoint, el último refresco del modelo de la app
  (`last_refresh_utc`) y si la capacidad ya está en ella (`capacity_in_app`), y el README pide comprobar el refresco.
- `model_workspace` puede llegar como GUID: `smgate run` y `NB_Gate_ModelReview` lo resuelven al nombre que necesita el
  orquestador para la dirección XMLA, en lugar de fallar en el test de carga.
- `teardown.ps1 -App` lista la base de datos SQL de la app y avisa de que se pierde su historial antes de pedir
  confirmación; la app muestra el rechazo del gate (actividad `Fail_Gate`) como aviso y no como fallo del pipeline;
  requisitos de capacidad mínima, refresco de Capacity Metrics y Node 20, 22 o 24 en el README.
- `npm run dev:demo` funciona en un checkout limpio: el cliente de Rayfin se crea al primer uso y no al importar.
