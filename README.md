# Lupus Vision

Prototipo académico para estudiar patrones faciales compatibles con manifestaciones cutáneas asociadas al lupus. El sistema no diagnostica lupus eritematoso sistémico (LES), no sustituye una valoración médica y no debe utilizarse para tomar decisiones clínicas.

## Estado

El proyecto se está reconstruyendo desde cero. La primera etapa implementa una compuerta de calidad, licencia y privacidad para impedir que un modelo sea entrenado con imágenes no autorizadas, duplicadas o separadas incorrectamente por fotografía.

Ninguna imagen facial, manifiesto identificable o modelo entrenado debe almacenarse en este repositorio.

## Flujo del proyecto

1. Documentar procedencia, licencia, consentimiento, sujeto y etiqueta de cada imagen.
2. Auditar integridad, metadatos, duplicados y fuga entre sujetos.
3. Congelar una partición por sujeto: entrenamiento, validación y prueba.
4. Entrenar una línea base reproducible mediante transferencia de aprendizaje.
5. Evaluar sensibilidad, especificidad, precisión, F1, ROC-AUC y calibración.
6. Exportar a LiteRT/TFLite y verificar equivalencia con Python.
7. Integrar el modelo validado en Android y probarlo en dispositivos reales.

## Preparación local

Requiere Python 3.11 o 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Auditoría del dataset

Copia `data/manifest.example.csv` fuera del repositorio, completa una fila por imagen y ejecuta:

```bash
lupus-data-audit \
  --manifest /ruta/segura/manifest.csv \
  --data-root /ruta/segura/dataset \
  --report artifacts/data-audit.json
```

El comando termina con código distinto de cero si encuentra un bloqueo. No debe iniciarse ningún entrenamiento mientras `ready_for_training` sea `false`.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

## Estructura

```text
android-app/              Aplicación móvil (se incorporará después del modelo validado)
data/                     Esquema y documentación; nunca fotografías reales
docs/                     Arquitectura y gobierno de datos
src/lupus_vision/data/    Auditoría reproducible del dataset
tests/                    Pruebas automatizadas
artifacts/                Reportes locales ignorados por Git
```

Consulta [docs/architecture.md](docs/architecture.md) y [docs/data-governance.md](docs/data-governance.md) antes de agregar datos o código de entrenamiento.
