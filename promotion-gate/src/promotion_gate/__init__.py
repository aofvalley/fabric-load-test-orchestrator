"""Gate de promoción de modelos semánticos de Power BI y Fabric (dev → prod).

Cuatro evidencias, un veredicto: revisión de buenas prácticas (BPA y VertiPaq), test de carga con el
Fabric Load Test Orchestrator, informe con recomendaciones y lectura del modelo de Capacity Metrics.
El núcleo es Python puro: se prueba fuera de Fabric y lo usan igual los notebooks, la CLI y el plugin.
"""

__version__ = "0.1.0"
