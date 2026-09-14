# Gobierno, privacidad y licencia de datos

Las fotografías faciales son datos biométricos potencialmente identificables. Cuando además están asociadas a una condición médica, requieren controles reforzados aunque el proyecto sea académico.

## Compuerta obligatoria

Cada archivo debe tener, antes del entrenamiento:

1. Fuente exacta y trazable.
2. Licencia que autorice expresamente el uso previsto, incluido entrenamiento y prueba de IA.
3. Base de consentimiento o distribución documentada.
4. Etiqueta sustentada y alcance clínico delimitado.
5. `subject_id` seudónimo.
6. Metadatos identificadores eliminados.
7. Partición asignada por sujeto.

Si cualquiera de estos puntos es desconocido, el archivo queda excluido.

## Repositorio

No se permiten en Git:

- fotografías originales o procesadas;
- manifiestos con nombres, coordenadas u otros identificadores;
- credenciales o archivos `.env`;
- modelos derivados de datos cuya licencia no permita distribución;
- consentimientos firmados.

Git conserva únicamente código, esquemas vacíos, pruebas con datos sintéticos y documentación no identificable.

## Curación científica

- No usar marcas de agua, rectángulos de censura o estilos de fuente exclusivos de una clase.
- No mezclar imágenes clínicas en una clase con fotografías de estudio en la otra.
- No tratar diferentes recortes o resoluciones como muestras independientes.
- Incluir controles negativos clínicamente relevantes cuando el protocolo lo permita.
- Documentar tono de piel, edad y sexo únicamente cuando exista base ética y metodológica para hacerlo.
- Revisar desempeño por subgrupos antes de cualquier afirmación de utilidad.

## Salida del sistema

La aplicación comunicará compatibilidad con un patrón visual y las limitaciones del prototipo. No mostrará una confirmación diagnóstica ni recomendará tratamientos.
