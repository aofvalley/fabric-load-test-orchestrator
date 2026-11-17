# Product

<!-- impeccable:product-schema 1 -->

> Se ha inferido del encargo («una Fabric App con Rayfin donde seleccionemos el modelo semántico o el informe, hagamos los tests y nos dé todo») y del gate existente en `../`. El usuario no pudo responder a la entrevista: todo lo marcado como *(supuesto)* está pendiente de confirmar.

## Platform

web

## Stack

Fabric App con Rayfin (SQL DB y GraphQL de la app, SSO de Fabric, hosting estático), React y TypeScript con Vite. Es el mismo stack que `operations-iq-poc`. Las llamadas a Fabric, Power BI y OneLake se hacen desde el navegador con un token delegado de MSAL; las tres APIs aceptan CORS (verificado el 2026-11-05).

## Users

- **Equipo de desarrollo de BI** (ingenieros de modelos semánticos) que cree que su modelo está listo y quiere saber si puede pasar a producción. Trabaja en su escritorio, entre sesiones de Power BI Desktop y Fabric. Lanza el gate, espera entre 30 y 60 minutos y vuelve a mirar el resultado.
- **Responsable de la plataforma o del CoE** *(supuesto)* que revisa veredictos, historial y aprueba la promoción.

## Product Purpose

Elegir un modelo semántico (y su informe), lanzar el gate de promoción completo y obtener, en una sola pantalla, el veredicto PASS, WARN o FAIL con su evidencia: buenas prácticas (BPA y VertiPaq), test de carga con rampa de usuarios, recomendaciones priorizadas y la lectura de Capacity Metrics. Si el veredicto lo permite, promocionar a producción con el deployment pipeline. Éxito: el equipo sabe en minutos de lectura qué falla, por qué y qué tocar, sin abrir notebooks ni ficheros.

## Positioning

La app no calcula nada: el veredicto lo produce el paquete `promotion_gate` en Fabric (el mismo que usan la CLI `smgate`, el plugin y el CI). La app solo prepara, lanza, sigue y presenta, así que el resultado es idéntico venga de donde venga. Usa la identidad del propio usuario: solo ve los modelos a los que tiene acceso.

## Operating Context

- Se abre dentro del portal de Fabric (iframe de la Fabric App) o en una pestaña propia.
- Piezas en Fabric: workspace de herramientas con lakehouse, `PL_PromotionGate`, notebooks `NB_Gate_*` y el Fabric Load Test Orchestrator (`PL_PerfTest_MultiModel_v3`).
- Evidencias por run en `Files/PromotionGate/runs/<run_id>/`: `verdict.json`, `model_review.json`, `loadtest.json`, `capacity.json` y `report.md`.
- El test de carga necesita un escenario de navegación: un JSON de Performance Analyzer exportado desde Power BI Desktop.

## Capabilities and Constraints

- Descubrir workspaces, modelos semánticos e informes enlazados al modelo.
- Escenario: subir el JSON de Performance Analyzer, reutilizar uno ya subido o generar uno sintético desde las medidas del modelo, marcado como de menor fidelidad *(supuesto: útil para un primer run)*.
- Configurar rampa, usuarios objetivo, think times, SKU de producción y SLO.
- Seguir el run por fases (revisión, carga, informe, Capacity Metrics y veredicto) mientras dura.
- Presentar veredicto, comprobaciones, recomendaciones, latencias por nivel, visuales lentas, BPA, VertiPaq y capacidad.
- Promocionar con deployment pipelines solo con `promotable = true` y confirmación explícita.
- Historial de runs en la base de datos de la app.
- Restricciones: un run dura entre 30 y 60 minutos; Capacity Metrics llega con 10 a 15 minutos de retraso; los umbrales del equipo viven en `config/gate.yaml` y la app no los relaja (solo propone un JSON por run, que queda registrado).

## Evidence on Hand

- Informe de ejemplo con datos sintéticos: `../docs/ejemplo-informe.md`.
- Contrato JSON de las evidencias: `../src/promotion_gate/` (verdict, loadtest, capacity, bpa).
- No hay clientes, capturas reales ni métricas de adopción: no inventarlos.

## Product Principles

1. La evidencia antes que la opinión: cada consejo muestra el dato que lo justifica.
2. El veredicto no se negocia en la interfaz: se puede leer, filtrar y explicar, nunca editar.
3. Una acción irreversible (promocionar) siempre pide confirmación con el modelo, el run y el destino a la vista.
4. Un run largo no deja al usuario a ciegas: siempre se ve en qué fase está y qué falta.
5. Español claro y operativo, sin jerga de marketing.

## Accessibility & Inclusion

WCAG 2.2 AA *(supuesto)*: contraste suficiente, estados que no dependen solo del color (PASS, WARN y FAIL siempre con texto e icono) y navegación completa con teclado.
