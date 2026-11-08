# Changelog del gate de promoción

El gate se versiona aparte del Fabric Load Test Orchestrator (`pyproject.toml`).

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
