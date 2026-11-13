# Laboratorio OES — Observatorio de Educación Superior (prototipo académico)

## Ejecutar
```
pip install streamlit pandas
python preparar_datos.py      # crea oes.db (se puede repetir sin duplicar)
streamlit run app.py          # http://localhost:8501
python pruebas.py             # pruebas P1-P6 + avanzadas (usa una copia temporal de la BD)
```

## Desplegar en Streamlit Community Cloud
1. Subir esta carpeta a un repositorio de GitHub (incluye `oes.db` y `requirements.txt`).
2. En https://share.streamlit.io → *Create app* → elegir el repositorio, rama `main`, archivo `app.py`.
   En *Advanced settings* elegir Python 3.12 o superior.
3. **Obligatorio:** en *Secrets* pegar `OES_CLAVE = "su-clave"` (ver `.streamlit/secrets.toml.example`).
   Con la clave configurada, quien no la conozca solo puede consultar; el modo edición se activa
   escribiéndola en la barra lateral. **Si se omite este paso, cualquiera podrá modificar los datos.**
4. Límite: lo que se registre desde la web se guarda en el servidor y **se pierde cuando la app se
   reinicia**. Para que un registro sea permanente, agréguelo en local y suba de nuevo `oes.db`.

Si `OES_CLAVE` no está configurada (uso local), la edición queda abierta sin contraseña.

## Qué incluye
| Nivel | Contenido |
|---|---|
| Básico | `oes.db`, `preparar_datos.py`, `app.py` (filtros, métricas, gráfico, CSV), evidencias P1–P6 (`evidencias_pruebas.txt`), capturas |
| Intermedio | BD normalizada (instituciones, fuentes, noticias), campos `fecha_captura`, `verificado_por`, `estado_verificacion`, filtro por rango de fechas |
| Avanzado | Alertas por palabras clave; resúmenes asistidos con revisión humana obligatoria; registro de cambios normativos; módulos de transparencia y calidad (estructura) |

## Límites que debes declarar en el informe
- Las 3 noticias, la norma y los indicadores cargados son **DEMOSTRATIVOS** (institución ficticia). Para la entrega, agrega registros reales desde la pestaña «Registrar noticia» tras verificar fecha y URL directa (prueba P6).
- Las alertas son coincidencia de texto, no análisis de contenido.
- El borrador de resumen es extractivo (local, sin API). Opcional: `OES_OLLAMA_MODEL=<modelo>` usa un LLM local con Ollama. Ningún borrador cuenta como verificado hasta que un revisor lo aprueba.
- No se copió código, identidad gráfica ni contenido del OES comercial.
