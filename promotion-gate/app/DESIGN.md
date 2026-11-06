---
name: Gate de promoción
description: Fabric App que inspecciona un modelo semántico y emite su certificado de aptitud para producción.
colors:
  paper: "#eef0eb"
  sheet: "#fbfbf9"
  sheet-2: "#f5f6f2"
  ink: "#15233f"
  ink-2: "#44526e"
  ink-3: "#5a6680"
  rule: "#cdd2da"
  rule-strong: "#15233f"
  rail: "#15233f"
  rail-ink: "#e6e9f0"
  rail-ink-2: "#9aa6bd"
  rail-active: "#24365b"
  stamp: "#2244c4"
  stamp-ink: "#ffffff"
  stamp-soft: "#e4e9fb"
  ok: "#1d7347"
  ok-stock: "#d7ecdf"
  ok-tag: "#1f7a4a"
  warn: "#7a4e00"
  warn-stock: "#f7dc7a"
  warn-tag: "#e9bd2f"
  fail: "#a8231a"
  fail-stock: "#f8d8d3"
  fail-tag: "#c8362a"
  skip: "#5d6a82"
  skip-stock: "#e3e6ec"
typography:
  display:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 760
    lineHeight: 1
    letterSpacing: "-0.015em"
    fontVariation: "'wdth' 68"
    fontFeature: "tnum"
  verdict:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.005em"
    fontVariation: "'wdth' 64"
  headline:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 680
    lineHeight: 1.2
  body:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    fontVariation: "'wdth' 100"
  body-sm:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 650
    letterSpacing: "0.06em"
    fontVariation: "'wdth' 72"
  mono:
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace"
    fontSize: "12px"
    lineHeight: 1.55
rounded:
  base: "3px"
  stock: "2px"
  stamp: "4px"
  tag-top: "6px"
  dialog: "6px"
spacing:
  sp-1: "4px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-5: "24px"
  sp-6: "32px"
  sp-7: "48px"
components:
  button-primary:
    backgroundColor: "{colors.stamp}"
    textColor: "{colors.stamp-ink}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "#1a37a6"
  button-secondary:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
    height: "38px"
  button-secondary-hover:
    backgroundColor: "{colors.sheet-2}"
  button-danger:
    backgroundColor: "#ffffff"
    textColor: "{colors.fail}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
  button-danger-hover:
    backgroundColor: "{colors.fail-stock}"
  input:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "8px 10px"
    height: "38px"
  input-disabled:
    backgroundColor: "{colors.sheet-2}"
    textColor: "{colors.ink-3}"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.base}"
  tag-pass:
    backgroundColor: "{colors.ok-stock}"
    textColor: "{colors.ok}"
    rounded: "{rounded.stock}"
    padding: "2px 9px 2px 7px"
  tag-warn:
    backgroundColor: "{colors.warn-stock}"
    textColor: "#4a3000"
    rounded: "{rounded.stock}"
    padding: "2px 9px 2px 7px"
  tag-fail:
    backgroundColor: "{colors.fail-stock}"
    textColor: "{colors.fail}"
    rounded: "{rounded.stock}"
    padding: "2px 9px 2px 7px"
  tag-skip:
    backgroundColor: "{colors.skip-stock}"
    textColor: "{colors.skip}"
    rounded: "{rounded.stock}"
    padding: "2px 9px 2px 7px"
  release-pass:
    backgroundColor: "{colors.ok-tag}"
    textColor: "#ffffff"
    padding: "30px 24px 24px"
  release-warn:
    backgroundColor: "{colors.warn-tag}"
    textColor: "#2b1c00"
    padding: "30px 24px 24px"
  release-fail:
    backgroundColor: "{colors.fail-tag}"
    textColor: "#ffffff"
    padding: "30px 24px 24px"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-ink-2}"
    width: "236px"
  rail-item-active:
    backgroundColor: "{colors.rail-active}"
    textColor: "#ffffff"
    rounded: "{rounded.base}"
---

# Design System: Gate de promoción

## Overview

**Creative North Star: "El certificado de aptitud para el servicio"**

Cada run es una inspección de aeronavegabilidad y su veredicto un certificado de aptitud para el servicio (EASA Form 1). La interfaz es papel de formulario frío con hojas casi blancas, tinta azul marino en el raíl y en los filetes, un sello ultramar que solo autoriza y cartulinas de color que cuelgan del modelo para decir su estado. Modo Operate: densidad de formulario, todo a la vista, nada decorativo que no sea parte del documento.

El mundo tiene tres objetos propios. La hoja con bloques numerados (los campos de un formulario). La etiqueta colgante del veredicto, con cordel, ojal reforzado y campos numerados, verde, amarilla o roja. Y el bloque de firma con su casilla rayada y el sello «Promocionado». El número de certificado es el titular de cada run; la ruta de fases deja a tinta plena solo la fase activa; las mejoras se priorizan con una escala fija de tamaños.

Se rechaza el dashboard de KPIs con tarjetas iguales y un semáforo: el estado vive en cartulinas con icono y palabra, y la única pieza grande y en color es el veredicto.

**Key Characteristics:**
- Papel `#eef0eb`, hojas `#fbfbf9`, tinta `#15233f`; esquinas de 3px y filetes de 1px.
- Ultramar `#2244c4` exclusivo para autorizar y para el foco.
- Estado siempre como cartulina con icono y palabra.
- Archivo variable con eje `wdth`: etiquetas condensadas en versalitas, cifras tabulares.
- Firma con confirmación escrita y sello.

## Colors

Paleta de oficina técnica: neutros fríos de papel y tinta, un único azul de sello y tres cartulinas de estado, cada una en tres intensidades (texto, cartulina clara, etiqueta llena).

### Primary
- **Sello ultramar** (#2244c4): botón primario («Lanzar gate», «Firmar y promocionar», «Firmar y desplegar»), contorno de `:focus-visible` (2px, desplazamiento 2px), borde de input con foco, opción de radio seleccionada, selección de texto, fase en curso de la ruta, número del bloque activo, enlaces y el sello «Promocionado». Hover del primario: #1a37a6.
- **Sello claro** (#e4e9fb): halo de foco de inputs (3px), fondo de opción seleccionada, halo de la fase en curso, nivel de carga en curso.
- **Tinta de sello** (#ffffff): texto sobre ultramar.

### Neutral
- **Papel frío** (#eef0eb): fondo de la aplicación y relleno del ojal de la etiqueta.
- **Hoja** (#fbfbf9): superficie de hojas, diálogos y punto vacío de la ruta.
- **Hoja gris** (#f5f6f2): barra inferior de resumen, filas en hover, inputs deshabilitados, avisos neutros.
- **Tinta marina** (#15233f): texto principal, filete fuerte (`rule-strong`), curva p95, rampa y filtros pulsados, pestaña activa.
- **Tinta media** (#44526e): texto secundario, etiquetas de campo, encabezados de tabla.
- **Tinta suave** (#5a6680): metadatos, números de bloque en reposo, fases no activas, curva p50, prioridad baja.
- **Filete** (#cdd2da): bordes de hojas, divisiones de bloques, rejilla del gráfico.
- **Raíl** (#15233f), **texto de raíl** (#e6e9f0), **texto de raíl apagado** (#9aa6bd), **raíl activo** (#24365b): navegación lateral.

### Estado (cartulinas)
- **Apto**: texto #1d7347, cartulina #d7ecdf, etiqueta #1f7a4a (etiqueta llena con texto blanco).
- **Observaciones**: texto #7a4e00, cartulina #f7dc7a (texto #4a3000), etiqueta #e9bd2f (texto #2b1c00).
- **No apto**: texto #a8231a, cartulina #f8d8d3, etiqueta #c8362a (etiqueta llena con texto blanco).
- **Sin datos / en curso**: texto #5d6a82, cartulina #e3e6ec. La etiqueta de veredicto en inspección usa #dfe3ea con tinta marina.

### Named Rules
**The Sello Rule.** El ultramar solo autoriza o señala foco. Nunca es decoración, nunca es estado, nunca es fondo de sección.

**The Cartulina Rule.** Un estado solo se pinta con su trío de cartulina (texto, cartulina, etiqueta). Verde, amarillo y rojo no se usan para nada que no sea apto, observaciones o no apto; el rojo #c8362a también marca el SLO y los puntos p95 por encima del SLO.

**The Raíl Rule.** Sobre el raíl azul marino, el foco y el indicador en vivo usan el amarillo de etiqueta (#e9bd2f), porque el ultramar no contrasta sobre marino. Es la única excepción a la Sello Rule.

## Typography

**Display Font:** Archivo Variable (eje `wdth`), con Archivo y system-ui de reserva.
**Body Font:** Archivo Variable a `wdth` 100.
**Mono Font:** JetBrains Mono Variable, solo para DAX, informe Markdown y código.

**Character:** Una sola familia que cambia de anchura según el papel: estrecha y pesada para el número de certificado y el veredicto, condensada en versalitas para los rótulos de campo, normal para leer.

### Hierarchy
- **Display** (760, 2.125rem, 1, `wdth` 68, cifras tabulares): número de certificado como titular del run. En móvil 1.625rem y corte en cualquier punto.
- **Veredicto** (800, 1.75rem, 1.02, `wdth` 64, mayúsculas): palabra del veredicto en la etiqueta colgante.
- **Headline** (700, 1.5rem, 1.2): título de página y de diálogo.
- **Title** (680, 1.125rem): título de bloque numerado; títulos de sección a 0.9375rem.
- **Body** (400, 0.9375rem, 1.5): texto corriente; párrafos limitados a 68 a 78ch.
- **Body pequeño** (0.8125rem): pistas, metadatos, tablas, avisos.
- **Label** (650 a 700, 0.6875rem, `wdth` 72 a 78, tracking 0.05 a 0.08em, mayúsculas): rótulos de campo, encabezados de tabla, campos `dt` de etiqueta, firma y `kv`, cartulinas de estado.
- **Mono** (12px, 1.55): bloques DAX y el informe.

### Named Rules
**The Cifra Tabular Rule.** Todo número que se compara (latencias, porcentajes, niveles, referencias, fechas) va con `font-variant-numeric: tabular-nums` (clase `.num`).

**The Mono Rule.** JetBrains Mono solo para DAX, código y el informe en bruto; nunca para cifras ni rótulos.

## Layout

Rejilla de aplicación de dos columnas: raíl fijo de 236px y área principal con relleno 32px arriba, 48px lados y abajo. La vista de run es `minmax(0, 1fr) 340px`: evidencias a la izquierda; a la derecha, columna pegajosa (top 24px) con la etiqueta del veredicto sobre el bloque de firma. Ritmo de espaciado en escala de 4px (4, 8, 12, 16, 24, 32, 48); el hueco entre piezas mayores es 24px.

El formulario de «Nuevo gate» es una sola hoja con bloques numerados 1 a 4 (columna de número de 52px y filete vertical) y una barra inferior de resumen con el botón primario grande.

**Responsive:**
- **≤1180px:** la columna del veredicto pasa encima del contenido (`order: -1`), deja de ser pegajosa y se reparte en dos columnas (etiqueta de hasta 340px y firma); relleno principal 24px.
- **≤860px:** el raíl se convierte en barra superior de dos filas (marca e insignia de datos sintéticos arriba; navegación con scroll horizontal debajo) y oculta nombre y usuario. Todo pasa a una columna: aside, rejillas, `kv`, cabecera del run, barra de resumen. La ruta de fases pasa a 3 columnas en 2 filas, el plan de fases a 2 columnas, la columna de número de bloque a 36px y el relleno de bloque a 16px.

## Elevation & Depth

Papel sobre mesa: casi plano. Las hojas se separan del papel con una sombra de contacto suave; solo la etiqueta del veredicto y el diálogo de firma se levantan de verdad.

### Shadow Vocabulary
- **Hoja** (`0 1px 2px rgba(21,35,63,0.06), 0 6px 18px -8px rgba(21,35,63,0.18)`): todas las hojas `.sheet`.
- **Etiqueta colgante** (`0 2px 3px rgba(21,35,63,0.12), 0 14px 28px -12px rgba(21,35,63,0.35)`): solo la etiqueta del veredicto.
- **Diálogo** (`0 30px 80px -20px rgba(21,35,63,0.55)`, fondo `rgba(21,35,63,0.45)` con desenfoque 2px): solo la confirmación de firma.

### Named Rules
**The Una Etiqueta Rule.** La sombra de etiqueta pertenece a un único objeto por pantalla: el veredicto.

## Shapes

Esquinas de formulario: 3px en hojas, botones, inputs, opciones y avisos; 2px en cartulinas y medidores; 4px en el sello; 6px en el diálogo. La etiqueta del veredicto tiene silueta propia: esquinas superiores de 6px recortadas en chaflán (`clip-path: polygon(14% 0, 86% 0, 100% 9%, 100% 100%, 0 100%, 0 9%)`), ojal de 16px y cordel SVG doble. Los puntos de la ruta y los marcadores de prioridad son círculos. Filetes de 1px; el filete fuerte marino solo enmarca la casilla de firma y la barra de resumen.

## Components

### Botones
- **Forma:** esquinas de 3px, alto mínimo 38px (46px en `--lg`), peso 600, icono de 16px a la izquierda.
- **Primario:** ultramar con texto blanco; hover #1a37a6. Uno por contexto: lanzar o firmar.
- **Secundario:** blanco con borde #b8bfcb; hover borde tinta suave y fondo hoja gris.
- **Peligro:** texto #a8231a con borde #e2a39c; hover cartulina roja. Solo «Cancelar run».
- **Silencioso:** sin borde ni fondo; hover tinta al 6%.
- **Pulsado / deshabilitado:** baja 1px al pulsar; deshabilitado con opacidad 0.55 y `not-allowed`.

### Cartulina de estado (`StatusTag`)
- Siempre icono de 13px más palabra: Apto (CircleCheck), Observaciones (TriangleAlert), No apto (OctagonX), Sin datos (CircleSlash), En curso (LoaderCircle girando 1.2s).
- Label condensada (700, `wdth` 78, mayúsculas), esquinas de 2px, colores de la Cartulina Rule.

### Inputs y opciones
- **Input / select:** blanco, borde #b8bfcb, 3px, alto 38px; hover borde tinta suave; foco borde ultramar más halo de 3px sello claro; deshabilitado en hoja gris con tinta suave. Error en texto #a8231a bajo el campo.
- **Opciones (radio):** casillas con borde filete; seleccionada con borde ultramar y fondo sello claro.
- **Rampa de niveles:** casillas de 52px de ancho mínimo; pulsada en tinta marina con texto blanco.
- **Filtros:** botones con `aria-pressed`; pulsado en tinta marina con texto blanco.

### Navegación (raíl)
- Fondo marino, ítems a 0.9375rem peso 520 en texto de raíl apagado; hover blanco al 6%; actual (`aria-current="page"`) en #24365b con texto blanco. Contador tabular a la derecha; punto amarillo pulsante para runs en vivo. Pie con insignia «Datos sintéticos» en cartulina amarilla.

### Bloques numerados (hoja de formulario)
- Columna de número (750, 1.125rem, `wdth` 70, tabular) separada por filete. Número en tinta suave en reposo, ultramar en el bloque activo, verde apto en el completado.

### Etiqueta del veredicto (`ReleaseTag`, firma del mundo)
- Cuelga de un cordel SVG doble (#8a93a5 y #a7aebd) y lleva un ojal reforzado: círculo del color del papel con sombra interior, anillo blanco al 55% y anillo exterior al 12%.
- Encabezado en label (Certificado de aptitud, Certificado condicionado, Etiqueta de rechazo, Inspección en curso), palabra de veredicto en tipo Veredicto y campos numerados en dos columnas bajo un filete del color del texto: 1. Certificado (ancho completo), 2. Modelo, 3. Workspace, 4. Emitido. Debajo, una fila por área con su cartulina, separadas por filete discontinuo.
- Llena del color de etiqueta: verde #1f7a4a, amarilla #e9bd2f, roja #c8362a; gris #dfe3ea mientras inspecciona.

### Bloque de firma (`signoff`)
- Título con icono de pluma: «Autorización de puesta en servicio».
- Casilla rayada con filete fuerte marino: referencia del certificado, firma de autorización (fila alta de 56px) y fecha. Sin firma muestra texto en cursiva tinta suave («La firma se habilita cuando el certificado sea apto»).
- Ruta de promoción origen → destino en dos casillas blancas.
- Firmar abre un diálogo que exige escribir el nombre del modelo; el botón final queda deshabilitado hasta que coincide.
- Promocionado: título «Puesto en servicio», firma en 760 y sello rotado -3°, borde ultramar de 2px, mayúsculas, que entra con `stamp-in`.

### Ruta de fases (`PhaseRoute`)
- Seis paradas con punto de 22px y conector de 2px. Hecha: punto y conector verde de etiqueta con check. Fallida: punto rojo de etiqueta con X. En curso: punto hoja con borde ultramar, halo de 4px y núcleo pulsante. Omitida: borde discontinuo. Pendiente: borde filete.
- Mientras hay una fase en curso, solo su nombre va a tinta plena (720); el resto queda en tinta suave. Cada parada lleva su estado en texto y duración. La fase de carga lista los niveles de la rampa en cartulinas.

### Marcadores de prioridad (`mag`)
- Escala fija de tamaños, no de longitud: alta círculo de 18px rojo de etiqueta, media 12px amarillo de etiqueta, baja 7px tinta suave. Siempre con `title` que dice la prioridad en texto.

### Gráfico de latencia (`LatencyChart`)
- SVG con eje X en niveles de usuarios, no en tiempo. p95 línea tinta marina de 2.5px con puntos llenos de 5px (rojo de etiqueta si superan el SLO); p50 línea discontinua tinta suave de 2px con puntos huecos; SLO línea discontinua roja de 1.5px rotulada. Rejilla en filete, eje en filete fuerte, cifras tabulares a 11px. Nivel objetivo en negrita; errores por nivel en rojo. `role="img"` con descripción completa y leyenda en texto.

### Otros
- **Pestañas:** subrayado de 2px en tinta marina para la activa; roles `tablist`/`tab`/`tabpanel`.
- **Tablas:** encabezados en label, celdas numéricas a la derecha y tabulares, filas clicables con hover hoja gris.
- **`kv`:** casillas de cifra (1.125rem, 680, tabular) con rótulo label; valor en rojo o ámbar si su estado lo pide.
- **Medidor:** barra de 8px sobre cartulina gris, relleno del color de etiqueta del estado y marca de límite marina.

### Estados
- **Carga:** esqueleto de 14px con brillo `shimmer` 1.3s lineal, con `aria-busy`.
- **Vacío:** hoja con título, explicación y una acción («Ver todos los runs»).
- **Error:** aviso `notice--fail` con icono, título fuerte y detalle; errores de campo en texto rojo; siempre con forma de reintentar.
- **Avisos:** neutro (hoja gris), observación (#fdf3d2), fallo (cartulina roja), correcto (cartulina verde); siempre icono de 18px más título.
- **Deshabilitado:** opacidad 0.55 en botones; inputs en hoja gris.

### Movimiento
- **Etiqueta:** `tag-in` 900ms `cubic-bezier(0.16, 1, 0.3, 1)`, balanceo desde el cordel (-7°, 3.2°, -1.1°, 0) con origen 30px por encima de la tarjeta. Se repite al cambiar el veredicto; no en inspección.
- **Sello:** `stamp-in` 420ms, de escala 1.35 y opacidad 0 a escala 1.
- **Transiciones:** 140 a 160ms con la misma curva en hovers y foco.
- **Movimiento reducido:** con `prefers-reduced-motion: reduce` todas las animaciones y transiciones quedan en 1ms y una iteración.

## Do's and Don'ts

### Do:
- **Do** expresar todo estado con icono más palabra en su cartulina (`StatusTag`).
- **Do** reservar el ultramar #2244c4 para la acción que autoriza y para el foco (2px, desplazamiento 2px).
- **Do** usar el número de certificado como titular del run, en Display condensada y tabular.
- **Do** numerar los bloques del formulario y los campos de la etiqueta.
- **Do** exigir el nombre del modelo escrito antes de firmar una promoción.
- **Do** etiquetar los datos de demostración como sintéticos en el raíl y en Ajustes.
- **Do** dar a cada gráfico una descripción textual completa en `aria-label` y una leyenda.
- **Do** mantener cifras tabulares en todo dato comparable.

### Don't:
- **Don't** construir paneles de tarjetas KPI iguales ni un semáforo; el único bloque grande en color es el veredicto.
- **Don't** usar el ultramar como decoración, fondo de sección o color de estado.
- **Don't** comunicar un estado solo con color.
- **Don't** usar verde, amarillo o rojo fuera de su significado de estado (o del SLO).
- **Don't** poner a tinta plena más de una fase cuando hay una en curso.
- **Don't** usar JetBrains Mono fuera de DAX, código y el informe.
- **Don't** aplicar la sombra de etiqueta a otro objeto que el veredicto.
- **Don't** usar esquinas mayores de 6px ni formas de píldora en piezas nuevas.
- **Don't** editar el veredicto desde la interfaz: viene del paquete `promotion_gate`.
