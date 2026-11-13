# TITAN Cloud R3.4 — versión web MVP 0.4

Esta versión adapta el motor experimental **TITAN-4.1-R3.4** para usarlo desde Chrome/Android sin instalar Python en el teléfono. **No está desplegada en Internet.** Es un proyecto ejecutable preparado para alojarse en una plataforma que admita Python/WSGI.

## Funciona hoy

- Panel móvil para introducir equipos y hora prevista; admite series BO3 y mecanismos documentados opcionales en JSON.
- Calcula una **selección provisional forzada**, identifica evidencia insuficiente y muestra los 12 controles pendientes. **No calcula probabilidades calibradas ni un ganador robusto.**
- Permite congelar una predicción **solo si el corte temporal está en el futuro**. Cada registro obtiene un ID único y se conserva la entrada original en SQLite.
- Permite registrar **una única vez** el ganador real, después del corte, sin modificar la predicción previa.
- Historial de últimas 100 predicciones.
- Autenticación HTTP Basic (usuario: `titan`, contraseña: variable `TITAN_PASSWORD`). Nunca envíes contraseñas por una conexión HTTP pública: en Internet es obligatorio HTTPS.

## No implementado todavía

- Conexiones autorizadas a HLTV u otras fuentes y verificación automática de URL.
- Descarga o interpretación automática de demos `.dem` (requiere parser real, archivos demo y trabajo de validación).
- Auditoría de 50 observaciones individuales, 10 reconstrucciones causales completas, anonimato procesal certificado, CIPI, HFE, CCE, PVE, BMA, MSI, SER, AME, DME, VSR, ECC.
- Vigilancia continua de próximos partidos o notificaciones. Son fases pendientes.

## Ejecución local (opcional, solo para desarrollar)

Python 3.10+ y biblioteca estándar:

```bash
export TITAN_PASSWORD='una-clave-larga-y-unica'
python cloud.py
```

Abrir `http://127.0.0.1:8765`, usuario `titan` y contraseña configurada. **No expongas este servidor de desarrollo públicamente.**

## Despliegue en un servicio web

1. Subir los archivos del proyecto al repositorio de GitHub elegido (sin claves ni bases de datos).
2. Abrir el enlace [Desplegar en Render](https://render.com/deploy?repo=https://github.com/julianalexanderriveragonzalez-commits/TITAN) y revisar que el único recurso sea un Web Service Free de $0. Para pruebas sin cargos por excedentes, usar un espacio gratuito sin método de pago.
3. Configurar `TITAN_PASSWORD` en Render. La plantilla usa `TITAN_DB=/tmp/titan.sqlite3`. El historial de prueba se pierde cuando la instancia se suspende, reinicia o vuelve a desplegarse.
4. Abrir la dirección HTTPS del servicio desde Android e iniciar sesión como `titan`.
5. Para varios usuarios hay que reemplazar Basic Auth por cuentas individuales y controles adicionales; **esta versión está pensada para uso personal.**

### Seguridad e integridad

Esta es una base MVP, no una infraestructura profesional completamente auditada. `TITAN_PASSWORD` es obligatorio. El servidor responde con política de no-caché y revisa Origin en POST. La contraseña HTTP Basic se reenvía en cada petición: usar siempre HTTPS cuando no se trate de loopback. SQLite debe conservarse en disco persistente; de lo contrario, se perderán los registros al reiniciarse el servidor. Un registro congelado solo es inmutable **a nivel de las rutas de esta aplicación**, no prueba criptográfica independiente de hora o autenticidad de evidencia. Para una prueba más fuerte se requiere almacenamiento externo append-only y sello de tiempo verificable. El motor utiliza todavía balance reciente de series como indicador exploratorio, lo cual **no satisface la versión final de los principios predictivos de TITAN**.

### Siguiente etapa de ingeniería

Conector de fuentes autorizadas -> validador de datos -> parser CS2 -> tabla de eventos y rondas -> motores causales -> pruebas de robustez -> evaluación prospectiva. No declarar módulos implementados sin sus tests y su verificación con demos reales.

## Pruebas

```bash
python -m unittest discover -s tests -v
```
