# Datos

Esta carpeta contiene únicamente documentación y ejemplos. Las imágenes reales y el manifiesto completo deben permanecer en almacenamiento privado con acceso controlado.

## Una fila por imagen

El manifiesto debe incluir:

- `image_id`: identificador único de la imagen.
- `subject_id`: identificador seudónimo estable de la persona.
- `label`: `control` o `pattern_compatible`.
- `clinical_label`: diagnóstico o condición reportada; no inferirla de la fotografía.
- `annotation_basis`: fundamento de la etiqueta, por ejemplo revisión dermatológica.
- `source_name`, `source_url`: procedencia verificable.
- `license_name`, `license_url`: licencia aplicable.
- `ai_use_allowed`: `yes` únicamente cuando la licencia permite entrenamiento y prueba de IA.
- `consent_status`: `licensed_public`, `research_consent` o `synthetic`.
- `has_watermark`: `yes`, `no` o `unknown`.
- `face_occluded`: `yes`, `no` o `unknown`.
- `split`: `train`, `validation`, `test` o `unassigned`.
- `relative_path`: ruta relativa dentro del almacenamiento privado.
- `sha256`: huella SHA-256 del archivo.
- `notes`: observaciones de curación.

## Reglas

- Una persona pertenece a un solo `split`.
- Una imagen y sus transformaciones pertenecen al mismo `split`.
- `original` y `resized` no son observaciones diferentes.
- Una imagen con licencia desconocida o sin autorización para IA no puede entrenarse.
- Las coordenadas GPS y otros metadatos identificadores deben eliminarse antes de cualquier uso.
- La etiqueta describe el patrón objetivo; no equivale a un diagnóstico de LES.
