# TITAN Cloud R3.4 — versión web MVP 0.4

Esta versión adapta el motor experimental **TITAN-4.1-R3.4** para usarlo desde Chrome/Android sin instalar Python en el teléfono. [Abrir el panel público](https://titan-cloud-r34-ite2.onrender.com/). Es un proyecto ejecutable preparado para alojarse en una plataforma que admita Python/WSGI.

## Funciona hoy

- Panel móvil para introducir equipos y hora prevista; admite series BO3 y mecanismos documentados opcionales en JSON.
- Calcula una **selección provisional forzada**, identifica evidencia insuficiente y muestra los 12 controles pendientes. **No calcula probabilidades calibradas ni un ganador robusto.**
- Permite congelar una predicción **solo si el corte temporal está en el futuro**. Cada registro obtiene un ID único y se conserva la entrada original en SQLite.
- Permite registrar **una única vez** el ganador real, después del corte, sin modificar la predicción previa.
- Acceso sin contraseña. Cada navegador conserva su propio historial temporal mediante una cookie. Los registros anteriores a este cambio quedan fuera del panel público.

## Investigación automática

El botón Investigar y analizar localiza equipos por su identificador en el directorio público de BLAST, confirma el cruce y la hora exacta de Colombia, y consulta hasta diez fichas por equipo. Verifica marcadores BO3 de los quince días anteriores, registra hasta cinco series por equipo y cuenta la participación de los jugadores de la plantilla publicada a partir de estadísticas por mapa. Cada antecedente conserva su URL. La cobertura se limita a las fichas disponibles. Un marcador inconsistente se excluye. Para Vitality–MOUZ del 13 de noviembre se incluye una captura de datos fechada antes del encuentro. El modo manual sigue disponible.

## No implementado todavía

- Auditoría automática multifuente de mecanismos causales.
- Descarga o interpretación automática de demos `.dem` (requiere parser real, archivos demo y trabajo de validación).
- Auditoría de 50 observaciones individuales, 10 reconstrucciones causales completas, anonimato procesal certificado, CIPI, HFE, CCE, PVE, BMA, MSI, SER, AME, DME, VSR, ECC.
- Vigilancia continua de próximos partidos o notificaciones. Son fases pendientes.

## Ejecución local (opcional, solo para desarrollar)

Python 3.10+ y biblioteca estándar:

```bash
python cloud.py
```

Abrir `http://127.0.0.1:8765`. **No expongas este servidor de desarrollo públicamente.**

## Despliegue en un servicio web

1. Subir los archivos del proyecto al repositorio de GitHub elegido (sin claves ni bases de datos).
2. Abrir el enlace [Desplegar en Render](https://render.com/deploy?repo=https://github.com/julianalexanderriveragonzalez-commits/TITAN) y revisar que el único recurso sea un Web Service Free de $0. Para pruebas sin cargos por excedentes, usar un espacio gratuito sin método de pago.
3. La plantilla usa `TITAN_DB=/tmp/titan.sqlite3`. El historial de prueba se pierde cuando la instancia se suspende, reinicia o vuelve a desplegarse.
4. Abrir la dirección HTTPS del servicio desde Android.

### Seguridad e integridad

Esta es una base MVP, no una infraestructura profesional completamente auditada. El servidor usa cookies HttpOnly, revisa Origin en POST y sirve la aplicación por HTTPS en Render. SQLite debe conservarse en disco persistente; de lo contrario, se perderán los registros al reiniciarse el servidor. Un registro congelado solo es inmutable **a nivel de las rutas de esta aplicación**, no prueba criptográfica independiente de hora o autenticidad de evidencia. Para una prueba más fuerte se requiere almacenamiento externo append-only y sello de tiempo verificable. El motor utiliza todavía balance reciente de series como indicador exploratorio, lo cual **no satisface la versión final de los principios predictivos de TITAN**.

### Siguiente etapa de ingeniería

Conector de fuentes autorizadas -> validador de datos -> parser CS2 -> tabla de eventos y rondas -> motores causales -> pruebas de robustez -> evaluación prospectiva. No declarar módulos implementados sin sus tests y su verificación con demos reales.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

## Auditoría por antecedente

En modo automático, TITAN busca las fichas de BO3.gg por equipo y fecha y comprueba rivales, nombres de mapa y marcadores desde la perspectiva de cada equipo. El informe cuenta fichas individuales de serie por nombre y fuente. Las estadísticas de ronda proceden de las tablas públicas por clan y se admiten cuando la secuencia y el marcador reconstruido coinciden. Una consulta posterior al corte queda en una revisión retrospectiva separada. La retirada individual de series prueba el indicador provisional. El resumen CIPI es descriptivo; conservar la etiqueta provisional mientras falten pruebas.

Para procesar un archivo original de demo en un entorno de análisis con Python 3.11 o posterior, instalar demoparser2==0.42.2 y ejecutar `python tools/parse_demo.py partida.dem salida.json`. El lector calcula aperturas, intercambios dentro de 320 ticks y equipamiento al terminar la compra. Los resultados incluyen huella SHA-256. La distribución del archivo original requiere una fuente accesible y atribución al mapa correcto. Las tablas por ronda de BO3.gg y la lectura directa de binarios tienen procedencias distintas.

### T1 y T2 en el análisis automático

La puntuación, la retirada de series, las fichas individuales y el diagnóstico CIPI usan identidades separadas de la evidencia de origen. El informe asigna Equipo A/B según el formulario y Jugador 1–5 por posición en la plantilla recibida. La correspondencia es propia del informe. Una plantilla incompleta o ambigua mantiene T1 parcial. T1 muestra nombres y fuentes en una vista documental separada del cálculo. Distingue plantilla publicada, titulares del encuentro y participantes de cada serie al corte y en revisión retrospectiva. El ganador provisional obligatorio se publica por separado.

T2 admite el inicio de la ventana de quince días y excluye la hora de corte. Normaliza las fechas a UTC, descarta duplicados y finales conocidos en el corte o posteriores y usa hasta cinco BO3 distintos por equipo. La pantalla diferencia la muestra individual prepartido de la corroboración posterior. La ejecución del filtro y la suficiencia de la muestra son verificaciones independientes.

### T3 — corroboración multifuente

El informe automático contrasta cada serie elegible de BLAST con BO3.gg. Por jugador compara el K-D agregado de todos los mapas de BLAST con el total de la serie en BO3.gg. Separa evidencia prepartido, revisión posterior, contradicciones, duplicados y carencias de cobertura. Para capturas antiguas usa la fecha de comprobación del lote como límite conservador. La corroboración de K-D no certifica ADR, intercambios ni atribuciones causales. El cálculo del pronóstico permanece independiente del expediente T3.

### Expediente T5 y seguimiento por fases

En modo automático, cada ficha enlaza los datos que T1–T4 atribuyen a la misma serie, separando el K-D prepartido y la corroboración posterior. El informe muestra las tres fases, las once tareas y la sensibilidad del indicador al cambiar una victoria por una derrota hipotética. La clasificación deportiva sigue siendo provisional cuando falta evidencia causal. El historial permite volver a abrir la copia congelada desde el mismo navegador mientras exista su registro en SQLite.

### T5 — piso colectivo y fuente del rating

La ficha de HLTV solo aporta rating de serie si coincide el BO3, la página identifica al equipo y la tabla de todos los mapas y ambos lados identifica explícitamente Rating 3.0. Cada participante real conserva rating, K-D, ADR, KAST, enlace y hora de consulta. Los valores estrictamente inferiores a 0,80 generan una alerta. La victoria del equipo no demuestra compensación. Una lectura posterior al corte queda fuera de la decisión previa.
