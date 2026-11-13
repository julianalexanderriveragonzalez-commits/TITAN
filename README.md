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
