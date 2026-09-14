# SCIN como fuente candidata

## Decisión

SCIN se incorpora como **fuente candidata A** para construir un repertorio inicial de
casos que después debe revisarse manualmente. No se considera, por sí solo, un dataset
válido para entrenar el clasificador facial de la tesis.

Fuentes oficiales:

- [Repositorio y ficha del dataset](https://github.com/google-research-datasets/scin)
- [Esquema de metadatos](https://github.com/google-research-datasets/scin/blob/main/dataset_schema.md)
- [Licencia de uso de SCIN](https://github.com/google-research-datasets/scin/blob/main/LICENSE)
- [Notebook oficial de exploración](https://github.com/google-research-datasets/scin/blob/main/scin_demo.ipynb)

La demostración oficial de la versión publicada muestra 31 casos con la etiqueta
ponderada `Cutaneous lupus`. Ese número representa casos, no imágenes faciales útiles.
Cada contribución puede contener hasta tres imágenes.

## Qué selecciona el inventario

`lupus-scin-inventory` cruza `scin_cases.csv` con `scin_labels.csv` por
`case_id` y conserva para revisión manual los casos que cumplen todas estas
condiciones:

1. La etiqueta ponderada incluye `Cutaneous lupus`.
2. `body_parts_head_or_neck` es verdadero.
3. Existe al menos una ruta de imagen.
4. Al menos una revisión dermatológica marcó el caso como gradable.

El resultado sigue llevando `training_status: not_approved`. El filtro cabeza/cuello
no prueba que el rostro sea visible, y la etiqueta `Cutaneous lupus` no prueba que la
imagen muestre eritema malar ni que la persona tenga diagnóstico confirmado de LES.

## Obtener únicamente los metadatos

El bucket y las rutas siguientes proceden del notebook oficial. Descarga primero los
dos CSV a una ubicación local segura; no los agregues al repositorio.

```bash
gcloud auth application-default login
gcloud storage cp gs://dx-scin-public-data/dataset/scin_cases.csv /ruta/segura/scin/
gcloud storage cp gs://dx-scin-public-data/dataset/scin_labels.csv /ruta/segura/scin/
```

También puede utilizarse el notebook oficial en Colab para obtener los mismos archivos
siguiendo su flujo de autenticación.

## Ejecutar el inventario

```bash
lupus-scin-inventory \
  --cases /ruta/segura/scin/scin_cases.csv \
  --labels /ruta/segura/scin/scin_labels.csv \
  --report artifacts/scin-inventory.json \
  --candidates artifacts/scin-candidates.csv
```

El JSON contiene conteos y decisiones del filtro. El CSV contiene una fila por imagen
candidata, con `case_id`, ruta, tipo de toma, peso de la etiqueta y número de votos
gradables. El comando no descarga fotografías.

## Revisión manual obligatoria

Antes de descargar o usar una fotografía candidata, una persona revisora debe registrar:

- si aparece realmente el rostro y si la zona malar es visible;
- si hay una manifestación compatible con el objetivo visual;
- oclusiones, maquillaje, iluminación y marca de agua;
- duplicados o múltiples tomas de la misma persona;
- fundamento de la etiqueta y cualquier incertidumbre.

El uso de SCIN debe respetar su licencia, incluida la atribución y la prohibición de
reidentificar o volver a vincular a los participantes. Esta nota documenta una decisión
técnica del proyecto y no sustituye asesoría jurídica o revisión ética.
