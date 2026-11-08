"""Caso de éxito del gate: un modelo listo para producción, con su informe y su escenario de navegación.

Crea en el workspace del gate una carpeta «Ventas Retail» con:
- lh_ventas_retail: lakehouse con esquemas y un esquema en estrella en Delta (datos ficticios, ~2 M de ventas).
- NB_Ventas_Retail_VOrder: reescribe esas tablas con V-Order (Direct Lake lo necesita para rendir).
- Ventas Retail (modelo semántico Direct Lake): claves enteras, importes en decimal fijo, relaciones de un solo sentido,
  claves ocultas, tabla de fechas marcada, medidas con DIVIDE, formato y descripción.
- Ventas Retail (informe PBIR): tres páginas.
- El escenario de navegación del informe (Files/PerfScenarios/Queries/Ventas_Retail_informe.json en el lakehouse del
  gate), con las consultas DAX de sus visuales y pausas entre clics. Todas se validan contra el modelo antes de subirlo.

Uso (Python x64 con numpy, pandas, pyarrow, deltalake y httpx):
    python demo/caso-exito/build.py --workspace-id <ws del modelo> --gate-lakehouse-id <lh_gate> [--gate-workspace-id <ws del gate>]
           [--subscription <sub>] [--only data|vorder|model|report|scenario]

El modelo debería vivir en otra capacidad que el workspace del gate: si comparten capacidad, los notebooks del
generador de carga cuentan en la misma capacidad y el gate lo marca como observación.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
from deltalake import write_deltalake

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "out" / "caso-exito"
FABRIC = "https://api.fabric.microsoft.com/v1"
PBI = "https://api.powerbi.com/v1.0/myorg"
FOLDER = "Ventas Retail"
LAKEHOUSE = "lh_ventas_retail"
MODEL = "Ventas Retail"
REPORT = "Ventas Retail"
SCENARIO = "Ventas_Retail_informe.json"
SEED = 20261105


# --------------------------------------------------------------------------------------------- API
class Api:
    def __init__(self, subscription: str | None, tenant: str | None):
        self.scope = ["--subscription", subscription] if subscription else (["--tenant", tenant] if tenant else [])
        self._tokens: dict[str, tuple[str, float]] = {}
        self.http = httpx.Client(timeout=180)

    def token(self, resource: str) -> str:
        cached = self._tokens.get(resource)
        if not cached or time.time() - cached[1] > 2400:
            out = subprocess.run(["az", "account", "get-access-token", "--resource", resource, *self.scope,
                                  "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, shell=sys.platform == "win32")
            if out.returncode != 0:
                raise SystemExit(f"Sin token para {resource}: {out.stderr.strip()}")
            self._tokens[resource] = (out.stdout.strip(), time.time())
        return self._tokens[resource][0]

    def call(self, method: str, url: str, resource="https://api.fabric.microsoft.com", ok404=False, headers=None, **kw) -> httpx.Response:
        for _ in range(40):
            h = {**(headers or {}), "Authorization": f"Bearer {self.token(resource)}"}
            r = self.http.request(method, url, headers=h, **kw)
            if r.status_code == 429 or (r.status_code in (409, 503) and '"isRetriable":true' in r.text.replace(" ", "")):
                time.sleep(max(int(r.headers.get("Retry-After", "0") or 0), 20))
                continue
            if ok404 and (r.status_code == 404 or "OperationHasNoResult" in r.text):
                return r
            if r.status_code >= 400:
                raise SystemExit(f"{method} {url} -> {r.status_code}: {r.text[:2000]}")
            return r
        raise SystemExit(f"{method} {url}: capacidad ocupada demasiado tiempo")

    def lro(self, r: httpx.Response) -> dict | None:
        if r.status_code != 202:
            return r.json() if r.content else None
        loc = r.headers["Location"]
        while True:
            time.sleep(int(r.headers.get("Retry-After", "3")))
            r = self.call("GET", loc)
            state = r.json().get("status")
            if state == "Succeeded":
                res = self.call("GET", loc.rstrip("/") + "/result", ok404=True)
                return res.json() if res.status_code < 400 and res.content else None
            if state in ("Failed", "Undefined"):
                raise SystemExit(f"Operación fallida: {r.text[:2000]}")


def find_item(api: Api, ws: str, kind: str, name: str) -> dict | None:
    items = api.call("GET", f"{FABRIC}/workspaces/{ws}/{kind}").json().get("value", [])
    return next((i for i in items if i["displayName"] == name), None)


def ensure_folder(api: Api, ws: str) -> str:
    folders = api.call("GET", f"{FABRIC}/workspaces/{ws}/folders").json().get("value", [])
    found = next((f for f in folders if f["displayName"] == FOLDER and not f.get("parentFolderId")), None)
    if found:
        return found["id"]
    return api.call("POST", f"{FABRIC}/workspaces/{ws}/folders", json={"displayName": FOLDER}).json()["id"]


def ensure_lakehouse(api: Api, ws: str, folder: str) -> str:
    lh = find_item(api, ws, "lakehouses", LAKEHOUSE)
    if lh:
        return lh["id"]
    res = api.lro(api.call("POST", f"{FABRIC}/workspaces/{ws}/lakehouses", json={
        "displayName": LAKEHOUSE, "folderId": folder, "description": "Ventas Retail: esquema en estrella (datos ficticios)",
        "creationPayload": {"enableSchemas": True}}))
    return (res or {}).get("id") or find_item(api, ws, "lakehouses", LAKEHOUSE)["id"]


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def upsert(api: Api, ws: str, kind: str, name: str, folder: str, parts: dict[str, str], description: str) -> str:
    payload = [{"path": p, "payload": b64(t), "payloadType": "InlineBase64"} for p, t in parts.items()]
    item = find_item(api, ws, kind, name)
    if item:
        api.lro(api.call("POST", f"{FABRIC}/workspaces/{ws}/{kind}/{item['id']}/updateDefinition", json={"definition": {"parts": payload}}))
        return item["id"]
    res = api.lro(api.call("POST", f"{FABRIC}/workspaces/{ws}/{kind}", json={
        "displayName": name, "description": description, "folderId": folder, "definition": {"parts": payload}}))
    return (res or {}).get("id") or find_item(api, ws, kind, name)["id"]


# --------------------------------------------------------------------------------------------- Datos
REGIONES = {
    "Centro": ["Madrid", "Toledo", "Guadalajara"], "Cataluña": ["Barcelona", "Girona", "Tarragona"],
    "Levante": ["Valencia", "Alicante", "Murcia"], "Andalucía": ["Sevilla", "Málaga", "Granada"],
    "Norte": ["Bilbao", "Santander", "Oviedo"], "Noroeste": ["A Coruña", "Vigo", "León"],
}
CATEGORIAS = {
    "Alimentación": (["Despensa", "Frescos", "Bebidas", "Congelados"], (1.5, 12)),
    "Hogar": (["Cocina", "Textil hogar", "Decoración", "Limpieza"], (4, 60)),
    "Moda": (["Mujer", "Hombre", "Infantil", "Calzado"], (9, 80)),
    "Electrónica": (["Telefonía", "Informática", "Imagen y sonido", "Pequeño electrodoméstico"], (25, 600)),
    "Deporte": (["Running", "Fitness", "Ciclismo", "Montaña"], (8, 150)),
}
MARCAS = ["Aurora", "Brisa", "Cumbre", "Delta", "Esencia", "Faro", "Garbo", "Horizonte"]
CANALES = ["Tienda", "Online", "App"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
START, END = date(2024, 1, 1), date(2026, 10, 31)


def money(values: np.ndarray) -> pa.Array:
    return pa.array(np.round(values, 2)).cast(pa.decimal128(18, 2), safe=False)


def build_data(rows: int) -> dict[str, pa.Table]:
    rng = np.random.default_rng(SEED)
    days = pd.date_range(START, END, freq="D")
    fecha = pd.DataFrame({"fecha": days.date})
    fecha["fecha_key"] = days.year * 10000 + days.month * 100 + days.day
    fecha["anio"] = days.year.astype(str)
    fecha["mes_num"] = days.month
    fecha["mes"] = [MESES[m - 1] for m in days.month]
    fecha["anio_mes"] = [f"{y}-{m:02d}" for y, m in zip(days.year, days.month)]
    fecha["trimestre"] = [f"T{(m - 1) // 3 + 1}" for m in days.month]
    fecha["dia_semana_num"] = days.day_of_week + 1
    fecha["dia_semana"] = days.day_name(locale=None).map({"Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles",
                                                          "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"})

    tiendas = []
    for region, ciudades in REGIONES.items():
        for ciudad in ciudades:
            for formato in ("Hipermercado", "Supermercado", "Proximidad"):
                tiendas.append({"tienda_key": len(tiendas) + 1, "tienda": f"{ciudad} {formato}", "ciudad": ciudad,
                                "region": region, "formato": formato})
    tienda = pd.DataFrame(tiendas)

    productos = []
    for categoria, (subs, (lo, hi)) in CATEGORIAS.items():
        for sub in subs:
            for i in range(20):
                marca = MARCAS[(len(productos) * 3 + i) % len(MARCAS)]
                precio = round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))), 2)
                productos.append({"producto_key": len(productos) + 1, "producto": f"{sub} {marca} {i + 1:02d}", "subcategoria": sub,
                                  "categoria": categoria, "marca": marca, "precio": precio,
                                  "margen": float(rng.uniform(0.18, 0.42))})
    producto = pd.DataFrame(productos)
    canal = pd.DataFrame({"canal_key": [1, 2, 3], "canal": CANALES})

    # Estacionalidad: diciembre y rebajas pesan más, fines de semana también, y el negocio crece un 6 % anual.
    w = np.ones(len(days))
    w *= np.where(days.month == 12, 1.6, 1.0) * np.where(days.month.isin([1, 7]), 1.25, 1.0) * np.where(days.month == 8, 0.85, 1.0)
    w *= np.where(days.day_of_week >= 5, 1.3, 1.0) * (1.06 ** ((days - days[0]).days / 365))
    d_idx = rng.choice(len(days), size=rows, p=w / w.sum())
    t_idx = rng.choice(len(tienda), size=rows, p=(lambda x: x / x.sum())(np.where(tienda.formato == "Hipermercado", 3.0,
                                                                                    np.where(tienda.formato == "Supermercado", 2.0, 1.0))))
    p_idx = rng.integers(0, len(producto), size=rows)
    c_idx = rng.choice(3, size=rows, p=[0.68, 0.22, 0.10])
    unidades = rng.integers(1, 6, size=rows)
    descuento = np.where(rng.random(rows) < 0.2, rng.choice([0.1, 0.15, 0.2, 0.3], size=rows), 0.0)
    precio = producto.precio.to_numpy()[p_idx]
    bruto = unidades * precio
    ventas = pa.table({
        "fecha_key": pa.array(fecha.fecha_key.to_numpy()[d_idx], pa.int64()),
        "tienda_key": pa.array(tienda.tienda_key.to_numpy()[t_idx], pa.int64()),
        "producto_key": pa.array(producto.producto_key.to_numpy()[p_idx], pa.int64()),
        "canal_key": pa.array(canal.canal_key.to_numpy()[c_idx], pa.int64()),
        "unidades": pa.array(unidades, pa.int64()),
        "importe": money(bruto * (1 - descuento)),
        "descuento": money(bruto * descuento),
        "coste": money(bruto * (1 - producto.margen.to_numpy()[p_idx])),
    })
    producto = producto.drop(columns=["margen"])
    producto["precio"] = producto["precio"].astype(object)
    to_pa = lambda df: pa.Table.from_pandas(df, preserve_index=False)
    prod_tbl = to_pa(producto.drop(columns=["precio"])).append_column("precio", money(producto.precio.astype(float).to_numpy()))
    fecha_tbl = to_pa(fecha.astype({"fecha_key": "int64", "mes_num": "int64", "dia_semana_num": "int64"}))
    return {"dim_fecha": fecha_tbl, "dim_tienda": to_pa(tienda), "dim_producto": prod_tbl, "dim_canal": to_pa(canal),
            "fact_ventas": ventas}


def load_data(api: Api, ws: str, lh: str, tables: dict[str, pa.Table]) -> None:
    opts = {"bearer_token": api.token("https://storage.azure.com"), "use_fabric_endpoint": "true"}
    for name, table in tables.items():
        write_deltalake(f"abfss://{ws}@onelake.dfs.fabric.microsoft.com/{lh}/Tables/dbo/{name}", table,
                        mode="overwrite", schema_mode="overwrite", storage_options=opts)
        print(f"  dbo.{name}: {table.num_rows:,} filas")


TABLES = ["dim_fecha", "dim_tienda", "dim_producto", "dim_canal", "fact_ventas"]
VORDER_NB = "NB_Ventas_Retail_VOrder"


def vorder(api: Api, ws: str, lh: str, folder: str) -> None:
    """delta-rs no escribe V-Order y OPTIMIZE no reescribe tablas de un solo fichero: las reescribe un notebook Spark
    (queda en la carpeta para repetir la carga) y luego se purgan los ficheros sin V-Order, que es lo que lee la regla BPA."""
    root = f"abfss://{ws}@onelake.dfs.fabric.microsoft.com/{lh}/Tables/dbo"
    code = [
        "# Reescribe las tablas de lh_ventas_retail con V-Order (Direct Lake lee mejor los Parquet con V-Order).\n",
        'spark.conf.set("spark.sql.parquet.vorder.default", "true")\n',
        f"root = \"{root}\"\n",
        f"for t in {TABLES!r}:\n",
        '    df = spark.read.format("delta").load(f"{root}/{t}").cache()\n',
        "    n = df.count()\n",
        '    df.write.format("delta").mode("overwrite").option("parquet.vorder.enabled", "true").save(f"{root}/{t}")\n',
        '    print(t, n, "filas reescritas con V-Order")\n',
    ]
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"language_info": {"name": "python"}, "kernel_info": {"name": "synapse_pyspark"}},
          "cells": [{"cell_type": "code", "source": code, "metadata": {}, "outputs": [], "execution_count": None}]}
    payload = [{"path": "notebook-content.ipynb", "payload": b64(json.dumps(nb)), "payloadType": "InlineBase64"}]
    item = find_item(api, ws, "notebooks", VORDER_NB)
    if item:
        api.lro(api.call("POST", f"{FABRIC}/workspaces/{ws}/notebooks/{item['id']}/updateDefinition?updateMetadata=false",
                         json={"definition": {"format": "ipynb", "parts": payload}}))
        nb_id = item["id"]
    else:
        res = api.lro(api.call("POST", f"{FABRIC}/workspaces/{ws}/notebooks", json={
            "displayName": VORDER_NB, "folderId": folder, "description": "Reescribe las tablas de Ventas Retail con V-Order",
            "definition": {"format": "ipynb", "parts": payload}}))
        nb_id = (res or {}).get("id") or find_item(api, ws, "notebooks", VORDER_NB)["id"]
    r = api.call("POST", f"{FABRIC}/workspaces/{ws}/items/{nb_id}/jobs/instances?jobType=RunNotebook", json={})
    loc = r.headers["Location"]
    while (job := api.call("GET", loc).json()).get("status") not in ("Completed", "Failed", "Cancelled", "Deduped"):
        time.sleep(15)
    if job.get("status") != "Completed":
        raise SystemExit(f"{VORDER_NB}: {job.get('status')} {job.get('failureReason')}")
    from deltalake import DeltaTable
    opts = {"bearer_token": api.token("https://storage.azure.com"), "use_fabric_endpoint": "true"}
    for t in TABLES:
        dt = DeltaTable(f"{root}/{t}", storage_options=opts)
        removed = dt.vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=False)
        print(f"  dbo.{t}: V-Order (versión {dt.version()}, {len(removed)} ficheros antiguos purgados)")


# --------------------------------------------------------------------------------------------- Modelo (TMDL)
def q(name: str) -> str:
    return name if name.replace("_", "").isalnum() and name.isascii() else "'" + name.replace("'", "''") + "'"


def hexid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def col(name, src, dtype, desc=None, *, hidden=False, fmt=None, sort_by=None, category=None, key=False, mdx=True):
    lines = [f"\t/// {desc}"] if desc else []
    lines.append(f"\tcolumn {q(name)}")
    lines.append(f"\t\tdataType: {dtype}")
    if key:
        lines.append("\t\tisKey")
    if hidden:
        lines.append("\t\tisHidden")
    if not mdx:
        lines.append("\t\tisAvailableInMdx: false")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append("\t\tsummarizeBy: none")
    if category:
        lines.append(f"\t\tdataCategory: {category}")
    if sort_by:
        lines.append(f"\t\tsortByColumn: {q(sort_by)}")
    lines.append(f"\t\tsourceColumn: {src}")
    return "\n".join(lines) + "\n\n"


def meas(name, dax, fmt, desc, folder=None):
    lines = [f"\t/// {desc}", f"\tmeasure {q(name)} = {dax.strip()}", f"\t\tformatString: {fmt}"]
    if folder:
        lines.append(f"\t\tdisplayFolder: {folder}")
    return "\n".join(lines) + "\n\n"


def part(table, entity):
    return (f"\tpartition {q(table)} = entity\n\t\tmode: directLake\n\t\tsource\n\t\t\tentityName: {entity}\n"
            f"\t\t\tschemaName: dbo\n\t\t\texpressionSource: {q('DirectLake Ventas Retail')}\n")


# Importes en euros con el formato que pide BPA (miles con separador); la moneda va en la descripción.
EUR = "#,0"
EUR2 = "#,0.00"
PCT = "#,0.0%;-#,0.0%;#,0.0%"
INT = "#,0"


def model_parts(ws: str, lh: str) -> dict[str, str]:
    tables = {
        "Fecha": "/// Calendario diario de enero de 2024 a octubre de 2026.\ntable Fecha\n\tdataCategory: Time\n\n"
        + col("Fecha", "fecha", "dateTime", "Día natural.", key=True, fmt="dd/mm/yyyy")
        + col("Fecha clave", "fecha_key", "int64", hidden=True, mdx=False, fmt="0")
        + col("Año", "anio", "string", "Año natural.")
        + col("Trimestre", "trimestre", "string", "Trimestre natural (T1 a T4).")
        + col("Mes número", "mes_num", "int64", hidden=True, fmt="0")
        + col("Mes", "mes", "string", "Mes natural.", sort_by="Mes número")
        + col("Año-mes", "anio_mes", "string", "Año y mes (AAAA-MM).")
        + col("Día de la semana número", "dia_semana_num", "int64", hidden=True, fmt="0")
        + col("Día de la semana", "dia_semana", "string", "Día de la semana.", sort_by="Día de la semana número")
        + part("Fecha", "dim_fecha"),
        "Tienda": "/// Tiendas de la cadena: 54 tiendas en 18 ciudades y 6 regiones.\ntable Tienda\n\n"
        + col("Tienda clave", "tienda_key", "int64", hidden=True, mdx=False, fmt="0", key=True)
        + col("Tienda", "tienda", "string", "Nombre de la tienda.")
        + col("Ciudad", "ciudad", "string", "Ciudad de la tienda.", category="City")
        + col("Región", "region", "string", "Región comercial.", category="StateOrProvince")
        + col("Formato", "formato", "string", "Hipermercado, Supermercado o Proximidad.")
        + part("Tienda", "dim_tienda"),
        "Producto": "/// Catálogo: 400 productos en 5 categorías y 20 subcategorías.\ntable Producto\n\n"
        + col("Producto clave", "producto_key", "int64", hidden=True, mdx=False, fmt="0", key=True)
        + col("Producto", "producto", "string", "Nombre del producto.")
        + col("Subcategoría", "subcategoria", "string", "Subcategoría del producto.")
        + col("Categoría", "categoria", "string", "Categoría del producto.")
        + col("Marca", "marca", "string", "Marca del producto.")
        + col("Precio de lista", "precio", "decimal", "Precio de venta al público sin descuento, en euros.", fmt=EUR2)
        + part("Producto", "dim_producto"),
        "Canal": "/// Canal de venta: Tienda, Online o App.\ntable Canal\n\n"
        + col("Canal clave", "canal_key", "int64", hidden=True, mdx=False, fmt="0", key=True)
        + col("Canal", "canal", "string", "Canal de venta.")
        + part("Canal", "dim_canal"),
        "Ventas": "/// Líneas de venta y medidas del negocio.\ntable Ventas\n\n"
        + meas("Ventas", "SUM ( Ventas[Importe] )", EUR, "Importe vendido en euros, neto de descuentos.")
        + meas("Coste", "SUM ( Ventas[Coste de venta] )", EUR, "Coste de la mercancía vendida, en euros.")
        + meas("Margen", "[Ventas] - [Coste]", EUR, "Ventas menos coste, en euros.")
        + meas("Margen %", "DIVIDE ( [Margen], [Ventas] )", PCT, "Margen sobre ventas.")
        + meas("Unidades", "SUM ( Ventas[Unidades vendidas] )", INT, "Unidades vendidas.")
        + meas("Precio medio", "DIVIDE ( [Ventas], [Unidades] )", "#,0.0", "Ventas por unidad vendida, en euros.")
        + meas("Descuento %", "DIVIDE ( SUM ( Ventas[Descuento aplicado] ), [Ventas] + SUM ( Ventas[Descuento aplicado] ) )", PCT,
               "Descuento sobre el importe bruto.")
        + meas("Ventas año anterior", "CALCULATE ( [Ventas], SAMEPERIODLASTYEAR ( Fecha[Fecha] ) )", EUR,
               "Ventas del mismo periodo del año anterior, en euros.", "Comparativa")
        + meas("Crecimiento %", "DIVIDE ( [Ventas] - [Ventas año anterior], [Ventas año anterior] )", PCT,
               "Variación de ventas frente al mismo periodo del año anterior.", "Comparativa")
        + meas("Cuota online %", 'DIVIDE ( CALCULATE ( [Ventas], Canal[Canal] IN { "Online", "App" } ), [Ventas] )', PCT,
               "Peso de los canales Online y App en las ventas.")
        + col("Fecha clave", "fecha_key", "int64", hidden=True, mdx=False, fmt="0")
        + col("Tienda clave", "tienda_key", "int64", hidden=True, mdx=False, fmt="0")
        + col("Producto clave", "producto_key", "int64", hidden=True, mdx=False, fmt="0")
        + col("Canal clave", "canal_key", "int64", hidden=True, mdx=False, fmt="0")
        + col("Unidades vendidas", "unidades", "int64", hidden=True, mdx=False, fmt=INT)
        + col("Importe", "importe", "decimal", hidden=True, mdx=False, fmt=EUR2)
        + col("Descuento aplicado", "descuento", "decimal", hidden=True, mdx=False, fmt=EUR2)
        + col("Coste de venta", "coste", "decimal", hidden=True, mdx=False, fmt=EUR2)
        + part("Ventas", "fact_ventas"),
    }
    rels = [("Ventas.'Fecha clave'", "Fecha.'Fecha clave'"), ("Ventas.'Tienda clave'", "Tienda.'Tienda clave'"),
            ("Ventas.'Producto clave'", "Producto.'Producto clave'"), ("Ventas.'Canal clave'", "Canal.'Canal clave'")]
    model = ["model Model", "\tculture: es-ES", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tdiscourageImplicitMeasures",
             "\tsourceQueryCulture: es-ES", ""] + [f"ref table {q(n)}" for n in tables]
    parts = {
        "definition.pbism": json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                        "version": "4.2", "settings": {}}, indent=2),
        "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n",
        "definition/model.tmdl": "\n".join(model) + "\n",
        "definition/expressions.tmdl": (
            "/// Origen Direct Lake: tablas Delta de lh_ventas_retail.\n"
            f"expression {q('DirectLake Ventas Retail')} =\n\t\tlet\n\t\t    Source = AzureStorage.DataLake(\"https://onelake.dfs.fabric.microsoft.com/{ws}/{lh}\", "
            "[HierarchicalNavigation=true])\n\t\tin\n\t\t    Source\n"),
        "definition/relationships.tmdl": "\n".join(f"relationship {hexid(a, b)[:20]}\n\tfromColumn: {a}\n\ttoColumn: {b}\n" for a, b in rels),
    }
    for name, body in tables.items():
        parts[f"definition/tables/{name}.tmdl"] = body
    return parts


# --------------------------------------------------------------------------------------------- Informe (PBIR) y escenario
SCHEMA_VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
SCHEMA_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
INK, ACCENT, MUTED = "#1F2A44", "#0F6E5C", "#9AA3B5"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def colref(e, p):
    return {"Column": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}


def measref(p):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "Ventas"}}, "Property": p}}


def proj(field, e, p, active=False):
    d = {"field": field, "queryRef": f"{e}.{p}", "nativeQueryRef": p}
    if active:
        d["active"] = True
    return d


def frame(title):
    return {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'"), "fontSize": lit("12D"), "bold": lit("true"),
                                      "fontColor": {"solid": {"color": lit(f"'{INK}'")}}}}],
            "border": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#E3E6EC'")}}, "radius": lit("6D")}}],
            "padding": [{"properties": {k: lit("10D") for k in ("top", "bottom", "left", "right")}}]}


class Page:
    """Una página del informe y, en paralelo, las consultas DAX que lanza al abrirse (las del escenario)."""

    def __init__(self, key: str, title: str):
        self.name, self.title, self.visuals, self.queries = hexid("page", key)[:20], title, [], []

    def add(self, vid, x, y, w, h, vtype, title, query_state, dax, objects=None, vco=None, sort=None):
        v = {"visualType": vtype, "query": {"queryState": query_state}, "drillFilterOtherVisuals": True}
        if sort:
            v["query"]["sortDefinition"] = {"sort": sort, "isDefaultSort": False}
        if objects:
            v["objects"] = objects
        v["visualContainerObjects"] = vco if vco is not None else frame(title)
        z = len(self.visuals) * 1000
        self.visuals.append({"$schema": SCHEMA_VC, "name": hexid(self.name, vid)[:20],
                             "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}, "visual": v})
        if dax:
            self.queries.append((title, hexid(self.name, vid)[:20], dax))

    def cards(self, vid, x, y, w, h, measures):
        qs = {"Data": {"projections": [proj(measref(m), "Ventas", m) for m in measures]}}
        cols = ", ".join(f'"{m}", [{m}]' for m in measures)
        objects = {"value": [{"properties": {"fontSize": lit("22D"), "fontColor": {"solid": {"color": lit(f"'{INK}'")}}}, "selector": {"id": "default"}}],
                   "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}]}
        self.add(vid, x, y, w, h, "cardVisual", "Indicadores", qs, f"EVALUATE ROW({cols})", objects,
                 {"border": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#E3E6EC'")}}, "radius": lit("6D")}}]})

    def chart(self, vid, x, y, w, h, vtype, title, cat, measures, sort_by_cat=False, top=None):
        e, p = cat
        qs = {"Category": {"projections": [proj(colref(e, p), e, p, active=True)]},
              "Y": {"projections": [proj(measref(m), "Ventas", m) for m in measures]}}
        sort = [{"field": colref(e, p) if sort_by_cat else measref(measures[0]), "direction": "Ascending" if sort_by_cat else "Descending"}]
        cols = ", ".join(f'"{m}", [{m}]' for m in measures)
        if sort_by_cat:
            dax = f"DEFINE VAR __DS0Core = SUMMARIZECOLUMNS('{e}'[{p}], {cols})\nEVALUATE __DS0Core ORDER BY '{e}'[{p}] ASC"
        else:
            dax = (f"DEFINE VAR __DS0Core = SUMMARIZECOLUMNS('{e}'[{p}], {cols})\n"
                   f"VAR __DS0PrimaryWindowed = TOPN({top or 1001}, __DS0Core, [{measures[0]}], 0)\n"
                   f"EVALUATE __DS0PrimaryWindowed ORDER BY [{measures[0]}] DESC, '{e}'[{p}] ASC")
        objects = {"dataPoint": [{"properties": {"fill": {"solid": {"color": lit(f"'{c}'")}}}, "selector": {"metadata": f"Ventas.{m}"}}
                                 for m, c in zip(measures, [ACCENT, MUTED, INK])],
                   "labels": [{"properties": {"show": lit("true" if vtype != "lineChart" else "false"), "fontSize": lit("9D")}}]}
        self.add(vid, x, y, w, h, vtype, title, qs, dax, objects, sort=sort)

    def table(self, vid, x, y, w, h, title, cols, measures):
        projs = [proj(colref(e, p), e, p) for e, p in cols] + [proj(measref(m), "Ventas", m) for m in measures]
        groups = ", ".join(f"'{e}'[{p}]" for e, p in cols)
        groups = f"ROLLUPGROUP({groups})" if len(cols) > 1 else groups
        mcols = ", ".join(f'"{m}", [{m}]' for m in measures)
        dax = (f"DEFINE VAR __DS0Core = SUMMARIZECOLUMNS(ROLLUPADDISSUBTOTAL({groups}, \"IsGrandTotalRowTotal\"), {mcols})\n"
               f"VAR __DS0PrimaryWindowed = TOPN(502, __DS0Core, [IsGrandTotalRowTotal], 0, [{measures[0]}], 0)\n"
               f"EVALUATE __DS0PrimaryWindowed ORDER BY [IsGrandTotalRowTotal] DESC, [{measures[0]}] DESC")
        self.add(vid, x, y, w, h, "tableEx", title, {"Values": {"projections": projs}}, dax,
                 sort=[{"field": measref(measures[0]), "direction": "Descending"}])

    def slicer(self, vid, x, y, w, h, title, cat):
        e, p = cat
        self.add(vid, x, y, w, h, "slicer", title, {"Values": {"projections": [proj(colref(e, p), e, p, active=True)]}},
                 f"EVALUATE SUMMARIZECOLUMNS('{e}'[{p}])",
                 {"data": [{"properties": {"mode": lit("'Basic'")}}], "selection": [{"properties": {"singleSelect": lit("false")}}]})

    def textbox(self, text, sub):
        paragraphs = [{"textRuns": [{"value": text, "textStyle": {"fontFamily": "Segoe UI Semibold", "fontSize": "20px", "color": INK}}]},
                      {"textRuns": [{"value": sub, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "11px", "color": "#5B6478"}}]}]
        v = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
             "visualContainerObjects": {"background": [{"properties": {"show": lit("false")}}]}}
        self.visuals.append({"$schema": SCHEMA_VC, "name": hexid(self.name, "title")[:20],
                             "position": {"x": 16, "y": 8, "z": 0, "width": 900, "height": 60, "tabOrder": 0}, "visual": v})


KPIS = ["Ventas", "Crecimiento %", "Margen %", "Unidades", "Cuota online %"]


def pages() -> list[Page]:
    p1 = Page("resumen", "Resumen")
    p1.textbox("Ventas Retail: resumen", "Ventas netas de descuentos. Datos ficticios de enero de 2024 a octubre de 2026.")
    p1.slicer("anio", 1000, 12, 264, 56, "Año", ("Fecha", "Año"))
    p1.cards("kpi", 16, 80, 1248, 110, KPIS)
    p1.chart("mes", 16, 202, 820, 250, "lineChart", "Ventas por mes", ("Fecha", "Año-mes"), ["Ventas", "Ventas año anterior"], sort_by_cat=True)
    p1.chart("region", 848, 202, 416, 250, "clusteredBarChart", "Ventas por región", ("Tienda", "Región"), ["Ventas"])
    p1.chart("categoria", 16, 464, 620, 248, "clusteredBarChart", "Ventas y margen por categoría", ("Producto", "Categoría"), ["Ventas", "Margen"])
    p1.chart("canal", 648, 464, 616, 248, "clusteredColumnChart", "Ventas por canal", ("Canal", "Canal"), ["Ventas"])

    p2 = Page("tiendas", "Tiendas")
    p2.textbox("Tiendas", "Rendimiento por tienda y formato.")
    p2.cards("kpi", 16, 80, 1248, 110, ["Ventas", "Margen %", "Precio medio", "Descuento %"])
    p2.table("tiendas", 16, 202, 820, 510, "Ranking de tiendas", [("Tienda", "Tienda"), ("Tienda", "Región")],
             ["Ventas", "Crecimiento %", "Margen %", "Cuota online %"])
    p2.chart("formato", 848, 202, 416, 250, "clusteredBarChart", "Ventas por formato", ("Tienda", "Formato"), ["Ventas"])
    p2.chart("dia", 848, 464, 416, 248, "clusteredColumnChart", "Ventas por día de la semana", ("Fecha", "Día de la semana"), ["Ventas"],
             sort_by_cat=True)

    p3 = Page("productos", "Productos")
    p3.textbox("Productos", "Qué se vende y con qué margen.")
    p3.chart("sub", 16, 80, 620, 632, "clusteredBarChart", "Ventas por subcategoría", ("Producto", "Subcategoría"), ["Ventas"])
    p3.table("top", 648, 80, 616, 400, "Productos más vendidos", [("Producto", "Producto")], ["Ventas", "Unidades", "Margen %"])
    p3.chart("marca", 648, 492, 616, 220, "clusteredColumnChart", "Margen por marca", ("Producto", "Marca"), ["Margen %"])
    return [p1, p2, p3]


def report_parts(model_id: str, pgs: list[Page]) -> dict[str, str]:
    theme = (HERE / "assets" / "Fluent2-CY26SU10.json").read_text(encoding="utf-8")
    ver = {"visual": "2.11.0", "report": "3.4.0", "page": "2.3.1"}
    parts = {
        "definition.pbir": json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                                       "version": "4.0", "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={model_id}"}}}),
        "definition/version.json": json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                                               "version": "2.0.0"}),
        "StaticResources/SharedResources/BaseThemes/Fluent2-CY26SU10.json": theme,
        "definition/report.json": json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
            "themeCollection": {"baseTheme": {"name": "Fluent2-CY26SU10", "reportVersionAtImport": ver, "type": "SharedResources"}},
            "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                                  "items": [{"name": "Fluent2-CY26SU10", "path": "BaseThemes/Fluent2-CY26SU10.json", "type": "BaseTheme"}]}],
            "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized", "defaultDrillFilterOtherVisuals": True,
                         "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}}),
        "definition/pages/pages.json": json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
                                                   "pageOrder": [p.name for p in pgs], "activePageName": pgs[0].name}),
    }
    for p in pgs:
        parts[f"definition/pages/{p.name}/page.json"] = json.dumps({"$schema": SCHEMA_PAGE, "name": p.name, "displayName": p.title,
                                                                    "displayOption": "FitToPage", "height": 720, "width": 1280})
        for v in p.visuals:
            parts[f"definition/pages/{p.name}/visuals/{v['name']}/visual.json"] = json.dumps(v, ensure_ascii=False)
    return parts


def with_year(dax: str, year: str) -> str:
    """La misma consulta con el segmentador de Año aplicado, como la genera Power BI."""
    flt = f'VAR __DS0FilterTable = TREATAS({{"{year}"}}, \'Fecha\'[Año])\n'
    if dax.startswith("EVALUATE ROW("):
        inner = dax[len("EVALUATE ROW("):-1]
        return f"DEFINE {flt}EVALUATE SUMMARIZECOLUMNS(__DS0FilterTable, {inner})"
    if "SUMMARIZECOLUMNS(" in dax and dax.startswith("DEFINE "):
        head, sep, rest = dax.partition("SUMMARIZECOLUMNS(")
        cut = rest.index(', "')  # los filtros van tras las columnas de agrupación y antes de las medidas
        return "DEFINE " + flt + (head + sep + rest[:cut] + ", __DS0FilterTable" + rest[cut:])[len("DEFINE "):]
    return dax


def scenario(pgs: list[Page]) -> dict:
    """Recorrido de un usuario: abre el resumen, filtra 2026, revisa tiendas y productos. Pausas de 6 a 14 s."""
    t = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    events = []
    iso = lambda d: d.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def visit(label, queries, pause):
        nonlocal t
        events.append({"name": "User Action", "start": iso(t), "end": iso(t + timedelta(milliseconds=50)), "metrics": {"sourceLabel": label}})
        for i, (title, vid, dax) in enumerate(queries):
            s = t + timedelta(milliseconds=100 + 20 * i)
            events.append({"name": "Visual Container Lifecycle", "start": iso(s), "end": iso(s + timedelta(milliseconds=400)),
                           "metrics": {"visualTitle": title, "visualId": vid}})
            events.append({"name": "Execute DAX Query", "start": iso(s + timedelta(milliseconds=10)), "end": iso(s + timedelta(milliseconds=300)),
                           "metrics": {"QueryText": dax}})
        t += timedelta(seconds=pause)

    p1, p2, p3 = pgs
    visit("Resumen", p1.queries, 12)
    visit("Resumen: Año 2026", [(ti, v, with_year(d, "2026")) for ti, v, d in p1.queries], 14)
    visit("Tiendas", p2.queries, 10)
    visit("Productos", p3.queries, 8)
    return {"version": "1.1.0", "synthetic": True, "source": "consultas de los visuales del informe Ventas Retail", "events": events}


def validate(api: Api, ws: str, model_id: str, sc: dict) -> None:
    queries = [e["metrics"]["QueryText"] for e in sc["events"] if e["name"] == "Execute DAX Query"]
    for dax in queries:
        print("  ·", dax.replace("\n", " ")[:110], flush=True)
        r = api.call("POST", f"{PBI}/groups/{ws}/datasets/{model_id}/executeQueries", resource="https://analysis.windows.net/powerbi/api",
                     json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}).json()
        res = r["results"][0]
        if res.get("error"):
            raise SystemExit(f"Consulta inválida:\n{dax}\n{res['error']}")
    print(f"  {len(queries)} consultas validadas contra el modelo")


def refresh(api: Api, ws: str, model_id: str) -> None:
    pbi = "https://analysis.windows.net/powerbi/api"
    api.call("POST", f"{PBI}/groups/{ws}/datasets/{model_id}/refreshes", resource=pbi, json={"type": "full"})
    while True:
        time.sleep(5)
        last = api.call("GET", f"{PBI}/groups/{ws}/datasets/{model_id}/refreshes?$top=1", resource=pbi).json()["value"][0]
        if last["status"] in ("Completed", "Failed", "Disabled", "Cancelled"):
            if last["status"] != "Completed":
                raise SystemExit(f"Refresh {last['status']}: {json.dumps(last)[:2000]}")
            return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--gate-lakehouse-id", required=True, help="Lakehouse del gate (lh_gate), donde se sube el escenario")
    ap.add_argument("--gate-workspace-id", help="Workspace del gate, si no es el del modelo")
    ap.add_argument("--subscription")
    ap.add_argument("--tenant")
    ap.add_argument("--rows", type=int, default=2_000_000)
    ap.add_argument("--only", choices=["data", "vorder", "model", "report", "scenario"])
    a = ap.parse_args()
    api, ws = Api(a.subscription, a.tenant), a.workspace_id
    steps = {a.only} if a.only else {"data", "model", "report", "scenario"}
    OUT.mkdir(parents=True, exist_ok=True)

    folder = ensure_folder(api, ws)
    lh = ensure_lakehouse(api, ws, folder)
    print(f"Carpeta {FOLDER} ({folder}), lakehouse {LAKEHOUSE} ({lh})")
    if "data" in steps:
        print("Datos")
        load_data(api, ws, lh, build_data(a.rows))
        vorder(api, ws, lh, folder)
    if steps == {"vorder"}:
        vorder(api, ws, lh, folder)
    if "model" in steps:
        print("Modelo semántico")
        mid = upsert(api, ws, "semanticModels", MODEL, folder, model_parts(ws, lh), "Ventas Retail: modelo Direct Lake en estrella")
        refresh(api, ws, mid)
        print(f"  {MODEL} ({mid}) creado y enmarcado")
    mid = find_item(api, ws, "semanticModels", MODEL)["id"]
    pgs = pages()
    if "report" in steps:
        print("Informe")
        rid = upsert(api, ws, "reports", REPORT, folder, report_parts(mid, pgs), "Ventas Retail: resumen, tiendas y productos")
        print(f"  {REPORT} ({rid})")
    if "scenario" in steps:
        print("Escenario de navegación")
        sc = scenario(pgs)
        validate(api, ws, mid, sc)
        text = json.dumps(sc, ensure_ascii=False, indent=1)
        (HERE / SCENARIO).write_text(text, encoding="utf-8")
        url = f"https://onelake.dfs.fabric.microsoft.com/{a.gate_workspace_id or ws}/{a.gate_lakehouse_id}/Files/PerfScenarios/Queries/{SCENARIO}"
        h = {"x-ms-version": "2023-11-03"}
        data = text.encode("utf-8")
        st = "https://storage.azure.com"
        api.call("PUT", f"{url}?resource=file", resource=st, headers=h, content=b"")
        api.call("PATCH", f"{url}?action=append&position=0", resource=st, headers=h, content=data)
        api.call("PATCH", f"{url}?action=flush&position={len(data)}", resource=st, headers=h, content=b"")
        print(f"  subido a Files/PerfScenarios/Queries/{SCENARIO}")
    (OUT / "deployment.json").write_text(json.dumps({"workspace_id": ws, "folder_id": folder, "lakehouse_id": lh, "model_id": mid},
                                                    indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
