# Aplicación Android

La aplicación se implementará después de aprobar el dataset, congelar el preprocesamiento y validar un modelo exportable.

Requisitos previstos:

- Kotlin y Jetpack Compose.
- Captura con CameraX.
- Inferencia local con LiteRT/TFLite.
- Preprocesamiento equivalente al pipeline Python.
- No conservar fotografías por defecto.
- Mensajes explícitamente no diagnósticos.
- Pruebas de paridad, latencia y memoria en al menos dos dispositivos.

No se agregan dependencias ni código Android en esta etapa para evitar fijar una interfaz alrededor de un modelo todavía no validado.
