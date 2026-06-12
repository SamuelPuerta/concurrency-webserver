# FIFO vs SFF: Análisis Completo de Resultados

## Resumen Ejecutivo

Se ejecutó una campaña experimental completa comparando dos políticas de scheduling
(FIFO y SFF) en un servidor web concurrente con thread pool. La campaña constó de
**3 escenarios × 2 políticas × 50 réplicas = 300 ejecuciones**, cada una de 60
segundos de duración. El servidor se ejecutó sobre un Intel Core i5-8400 (6 núcleos).

### Hallazgos principales

1. **Latencia**: Ambos schedulers producen latencias prácticamente idénticas en
   todos los escenarios. Las diferencias estadísticamente significativas existen
   (Escenario A y C), pero son de magnitud despreciable (~0.001 ms).
2. **Throughput**: Ambos schedulers alcanzan el límite teórico de la tasa
   configurada (~100 req/s en A/B, ~500 req/s en C) sin errores.
3. **Fairness**: Ambos schedulers presentan coeficientes de variación bajos
   (< 0.01 en Escenario A, ~0.015 en B).
4. **Conclusión**: En esta implementación, **no hay una ventaja práctica de SFF
   sobre FIFO ni viceversa**. La política de scheduling no impacta el rendimiento
   bajo las cargas evaluadas.

---

## Configuración Experimental

### Parámetros

| Parámetro | Escenario A | Escenario B | Escenario C |
|-----------|:-----------:|:-----------:|:-----------:|
| Ratio small/large | 100% / 0% | 70% / 30% | 80% / 20% |
| Tasa de requests | 100 req/s | 100 req/s | 500 req/s |
| Duración | 60 s | 60 s | 60 s |
| Threads del servidor | 8 | 8 | 12 |
| Tamaño buffer | 16 | 16 | 16 |
| Workers del cliente | 64 | 64 | 64 |
| Réplicas por política | 50 | 50 | 50 |

### Archivos de prueba

- **Small**: 10 KB cada uno (50 archivos)
- **Large**: 500 KB cada uno (20 archivos)

---

## Resultados por Escenario

### Escenario A: Carga Homogénea (100% small)

#### Estadísticas descriptivas

| Métrica | FIFO (n=50) | SFF (n=50) |
|---------|:-----------:|:----------:|
| Latencia media (ms) | 0.415 ± 0.002 | 0.414 ± 0.001 |
| Mediana latencia (ms) | 0.414 | 0.414 |
| p95 latencia (ms) | 0.418 | 0.415 |
| p99 latencia (ms) | 0.425 | 0.416 |
| CV latencia | 0.006 | 0.002 |
| Throughput (req/s) | 99.996 ± 0.003 | 99.996 ± 0.002 |

#### Prueba estadística (Mann-Whitney U)

| Métrica | U | p-valor | Efecto (r) | Interpretación |
|---------|:-:|:-------:|:----------:|----------------|
| Latencia | 1624.5 | 0.0053 ** | −0.300 (pequeño) | SFF tiene latencia ligeramente menor |
| Throughput | 1211.0 | 0.7888 ns | +0.031 (insignificante) | Sin diferencia significativa |

#### Análisis

- Ambos schedulers manejan los 6000 requests (100 req/s × 60 s) sin errores.
- Las latencias son extremadamente bajas (~0.41 ms) dado que solo se sirven
  archivos pequeños de 10 KB.
- La diferencia en latencia media es de ~0.001 ms, estadísticamente significativa
  (p=0.005) pero **irrelevante en la práctica**.
- SFF presenta menor variabilidad (CV=0.002 vs 0.006), aunque ambas son mínimas.
- El throughput alcanza exactamente la tasa configurada (~100 req/s) sin
  diferencias entre políticas.

---

### Escenario B: Carga Heterogénea (70% small, 30% large)

#### Estadísticas descriptivas

| Métrica | FIFO (n=50) | SFF (n=50) |
|---------|:-----------:|:----------:|
| Latencia media (ms) | 0.549 ± 0.008 | 0.550 ± 0.010 |
| Mediana latencia (ms) | 0.546 | 0.546 |
| p95 latencia (ms) | 0.563 | 0.564 |
| p99 latencia (ms) | 0.565 | 0.576 |
| CV latencia | 0.015 | 0.018 |
| Throughput (req/s) | 99.995 ± 0.002 | 99.996 ± 0.002 |

#### Latencia por tipo de archivo

| Tipo | FIFO mean (ms) | FIFO p95 (ms) | SFF mean (ms) | SFF p95 (ms) |
|------|:--------------:|:-------------:|:-------------:|:------------:|
| Small (10 KB) | 0.421 | 0.483 | 0.421 | 0.484 |
| Large (500 KB) | 0.836 | 0.975 | 0.839 | 0.977 |

#### Prueba estadística (Mann-Whitney U)

| Métrica | U | p-valor | Efecto (r) | Interpretación |
|---------|:-:|:-------:|:----------:|----------------|
| Latencia | 1205.0 | 0.7587 ns | +0.036 (insignificante) | Sin diferencia significativa |
| Throughput | 956.0 | 0.0415 * | +0.235 (pequeño) | SFF tiene throughput ligeramente mayor |

#### Análisis

- La latencia media (~0.55 ms) es mayor que en A debido a los archivos grandes
  de 500 KB (~0.84 ms vs ~0.42 ms para small).
- No hay diferencia estadísticamente significativa en latencia entre FIFO y SFF
  (p=0.759).
- El throughput nuevamente alcanza el máximo teórico (~100 req/s).
- La prueba de throughput sugiere una ventaja para SFF (p=0.041), pero la
  magnitud es insignificante (diferencia de 0.001 req/s).
- El CV más alto (~0.015) refleja la distribución bimodal (small + large).
- **Contraintuitivo**: SFF debería priorizar archivos small sobre large, pero
  no se observa mejora en latencia. Esto sugiere que el cuello de botella no
  es la selección de la cola sino el I/O (lectura de disco/red).

---

### Escenario C: Estrés (500 req/s, 80% small, 20% large)

#### Estadísticas descriptivas

| Métrica | FIFO (n=50) | SFF (n=50) |
|---------|:-----------:|:----------:|
| Latencia media (ms) | 0.491 ± 0.002 | 0.490 ± 0.002 |
| Mediana latencia (ms) | 0.491 | 0.490 |
| p95 latencia (ms) | 0.495 | 0.495 |
| p99 latencia (ms) | 0.497 | 0.496 |
| CV latencia | 0.004 | 0.005 |
| Throughput (req/s) | 499.995 ± 0.003 | 499.996 ± 0.003 |

#### Prueba estadística (Mann-Whitney U)

| Métrica | U | p-valor | Efecto (r) | Interpretación |
|---------|:-:|:-------:|:----------:|----------------|
| Latencia | 1545.5 | 0.0395 * | −0.236 (pequeño) | FIFO tiene latencia ligeramente menor |
| Throughput | 892.5 | 0.0132 * | +0.286 (pequeño) | SFF tiene throughput ligeramente mayor |

#### Análisis

- Se despacharon 30000 requests por réplica (500 req/s × 60 s) sin errores
  en ninguna réplica.
- La latencia media (~0.49 ms) es **menor que en el Escenario B** (0.55 ms) a
  pesar de tener 5× la tasa de requests. Esto se explica por los 12 threads
  (vs 8 en B) que permiten mayor paralelismo y porque la proporción de archivos
  large es menor (20% vs 30%).
- FIFO muestra latencia ligeramente menor que SFF (p=0.039), pero la diferencia
  es de ~0.001 ms — irrelevante.
- SFF muestra throughput ligeramente mayor (p=0.013) — también irrelevante en
  magnitud.
- El servidor mantiene la tasa de 500 req/s establemente, sin pérdida de
  requests ni errores.

---

## Comparativa entre Escenarios

### Throughput

```
Escenario   | Tasa configurada | FIFO (media) | SFF (media) | % alcanzado
------------|:----------------:|:------------:|:-----------:|:-----------:
A           | 100 req/s        | 99.996       | 99.996      | ~100%
B           | 100 req/s        | 99.995       | 99.996      | ~100%
C           | 500 req/s        | 499.995      | 499.996     | ~100%
```

Todos los escenarios alcanzan el 100% del throughput configurado. El servidor
no muestra signos de saturación ni pérdida de requests.

### Latencia

```
Escenario   | FIFO mean (ms) | SFF mean (ms) | Diferencia | Significativa?
------------|:--------------:|:-------------:|:----------:|:-------------:
A           | 0.415          | 0.414         | 0.001      | Sí (p=0.005)
B           | 0.549          | 0.550         | −0.001     | No (p=0.759)
C           | 0.491          | 0.490         | 0.001      | Sí (p=0.040)
```

La latencia en B es la más alta debido a la mayor proporción de archivos large
(30%). En C, con 12 threads y solo 20% large, la latencia es comparable a A.

### Fairness (CV de latencia)

```
Escenario   | FIFO CV | SFF CV
------------|:-------:|:------:
A           | 0.006   | 0.002
B           | 0.015   | 0.018
C           | 0.004   | 0.005
```

SFF tiene CV ligeramente menor en A (más homogéneo), pero FIFO tiene CV
ligeramente menor en B y C. Las diferencias son marginales.

---

## Pruebas de Normalidad (Shapiro-Wilk)

| Escenario | Política | Métrica | W | p-valor | ¿Normal? |
|-----------|:--------:|:-------:|:-:|:-------:|:--------:|
| A | FIFO | Latencia | — | 0.0000 | **No** |
| A | SFF | Latencia | — | 0.0001 | **No** |
| B | FIFO | Latencia | — | 0.0031 | **No** |
| B | SFF | Latencia | — | 0.0021 | **No** |
| C | FIFO | Latencia | — | 0.1760 | **Sí** |
| C | SFF | Latencia | — | 0.0001 | **No** |

La mayoría de los grupos no siguen una distribución normal, lo que justifica
el uso de la prueba no paramétrica Mann-Whitney U en lugar de t-student.

---

## Efectos de Tamaño (Rank-Biserial r)

| Escenario | Métrica | r | Interpretación |
|-----------|:-------:|:-:|:--------------:|
| A | Latencia | −0.300 | Pequeño |
| A | Throughput | +0.031 | Insignificante |
| B | Latencia | +0.036 | Insignificante |
| B | Throughput | +0.235 | Pequeño |
| C | Latencia | −0.236 | Pequeño |
| C | Throughput | +0.286 | Pequeño |

Todos los efectos significativos son de magnitud **pequeña** (r entre 0.2 y
0.3), lo que refuerza que las diferencias, aunque detectables estadísticamente,
no son relevantes en la práctica.

---

## Anomalías Detectadas

Durante la inspección de datos se observaron valores atípicos en la columna
`fairness_cv` (coeficiente de variación entre requests individuales dentro
de una réplica):

| Réplica | fairness_cv | Posible causa |
|---------|:-----------:|---------------|
| B, SFF, réplica 4 | 4.584 | Alta variabilidad intra-réplica |
| C, SFF, réplica 6 | 2.374 | Alta variabilidad intra-réplica |
| C, SFF, réplica 28 | 2.471 | Alta variabilidad intra-réplica |

Estos valores son órdenes de magnitud mayores que el resto (típicamente
< 0.4). Se recomienda investigar si hubo interferencia del sistema operativo
(por ejemplo, procesos en segundo plano, throttling de CPU) durante esas
réplicas.

---

## Conclusiones

1. **SFF no ofrece ventajas sobre FIFO** en esta implementación. La política
   de scheduling de la cola interna no afecta significativamente el rendimiento
   bajo las condiciones evaluadas.

2. **El cuello de botella no es la selección de la cola**. Dado que tanto FIFO
   (O(1)) como SFF (O(n)) producen resultados casi idénticos, el tiempo de
   servicio está dominado por la lectura de archivos del disco y la transmisión
   por red, no por la política de scheduling.

3. **El servidor escala correctamente**: de 100 a 500 req/s, mantiene el
   throughput sin pérdidas ni errores, con latencias estables.

4. **La diferencia small vs. large** es el factor dominante en la latencia:
   archivos large (500 KB) toman ~2× más tiempo que archivos small (10 KB),
   independientemente de la política.

5. **Para cargas de trabajo reales**, donde los archivos grandes no pueden
   ignorarse, se recomienda explorar:
   - Políticas adicionales (prioridad por tipo de archivo, fairness ponderada)
   - Timeouts o límites de tamaño en la cola
   - Múltiples colas con prioridades
