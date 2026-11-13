import hmac
import os

import pandas as pd
import streamlit as st

import oes_core as oes

st.set_page_config(page_title="OES académico", layout="wide")
st.title("Observatorio de Educación Superior — Prototipo académico")
st.caption("Registros didácticos; confirmar fuentes antes de uso institucional")


# ------------------------------------------------------------------ modo edición (contraseña)
def _clave_configurada():
    """Clave de edición: secreto OES_CLAVE (Streamlit Cloud) o variable de entorno.
    Si no hay ninguna (uso local), la edición queda habilitada sin contraseña."""
    try:
        if "OES_CLAVE" in st.secrets:
            return str(st.secrets["OES_CLAVE"])
    except Exception:  # no existe secrets.toml
        pass
    return os.environ.get("OES_CLAVE") or None


CLAVE = _clave_configurada()
if CLAVE is None:
    PUEDE_EDITAR = True
    st.sidebar.caption("Modo local: edición sin contraseña (OES_CLAVE no configurada).")
else:
    if not st.session_state.get("editor"):
        intento = st.sidebar.text_input("Clave de edición", type="password", key="clave_edicion")
        if intento and hmac.compare_digest(intento.encode(), CLAVE.encode()):
            st.session_state["editor"] = True
        elif intento:
            st.sidebar.error("Clave incorrecta.")
    PUEDE_EDITAR = bool(st.session_state.get("editor"))
    if PUEDE_EDITAR:
        st.sidebar.success("Modo edición activo.")
        if st.sidebar.button("Salir del modo edición"):
            st.session_state["editor"] = False
            st.rerun()


def solo_lectura():
    st.info("Solo lectura. Ingrese la clave de edición en la barra lateral para modificar datos.")

if not oes.DB.exists():
    st.warning("No existe la base. Ejecute: python preparar_datos.py")
    st.stop()

con = oes.conectar()
df = pd.read_sql_query("SELECT * FROM v_noticias ORDER BY fecha DESC", con)
if df.empty:
    st.warning("No hay noticias. Ejecute preparar_datos.py")
    st.stop()

# ------------------------------------------------------------------ filtros (RF02)
categorias = sorted(df["categoria"].unique().tolist())
seleccion = st.sidebar.multiselect("Categoría", categorias, default=categorias)
estados = st.sidebar.multiselect("Estado de verificación", oes.ESTADOS_VERIF,
                                 default=oes.ESTADOS_VERIF)
busqueda = st.sidebar.text_input("Buscar título o institución")
f_min, f_max = pd.to_datetime(df["fecha"]).min().date(), pd.to_datetime(df["fecha"]).max().date()
rango = st.sidebar.date_input("Rango de fechas", value=(f_min, f_max))
desde, hasta = (rango[0], rango[1]) if len(rango) == 2 else (rango[0], rango[0])

filtrado = oes.filtrar(df, seleccion, busqueda, desde, hasta, estados)

tab_n, tab_a, tab_r, tab_c, tab_t, tab_add = st.tabs(
    ["Noticias", "Alertas", "Resúmenes (IA + revisión)", "Cambios normativos",
     "Transparencia y calidad", "Registrar noticia"])

# ------------------------------------------------------------------ noticias (RF01-RF04)
with tab_n:
    ind = oes.indicadores(filtrado)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Noticias", ind["noticias"])
    c2.metric("Instituciones", ind["instituciones"])
    c3.metric("Categorías", ind["categorias"])
    c4.metric("Verificadas", ind["verificadas"])

    st.subheader("Distribución por categoría")
    if not filtrado.empty:
        st.bar_chart(filtrado["categoria"].value_counts())
    else:
        st.info("No hay resultados con esos filtros")

    st.subheader("Noticias registradas")
    st.dataframe(filtrado[["fecha", "institucion", "categoria", "titulo", "fuente", "url",
                           "fecha_captura", "estado_verificacion", "verificado_por"]],
                 width="stretch", hide_index=True)
    st.download_button("Exportar CSV", data=filtrado.to_csv(index=False).encode("utf-8-sig"),
                       file_name="oes_resultados.csv", mime="text/csv")

# ------------------------------------------------------------------ alertas por palabras clave
with tab_a:
    st.write("Una alerta es una **coincidencia de texto** con una palabra clave "
             "(sin tildes ni mayúsculas); no interpreta el contenido.")
    palabras_bd = [r["palabra"] for r in con.execute(
        "SELECT palabra FROM alertas_palabras WHERE activa = 1 ORDER BY palabra")]
    if PUEDE_EDITAR:
        nueva = st.text_input("Agregar palabra clave", key="nueva_palabra")
        if st.button("Agregar palabra") and nueva.strip():
            con.execute("INSERT OR IGNORE INTO alertas_palabras (palabra) VALUES (?)", (nueva.strip(),))
            con.commit()
            st.rerun()
    activas = st.multiselect("Palabras vigiladas", palabras_bd, default=palabras_bd)
    alertas = pd.DataFrame(oes.detectar_alertas(filtrado, activas))
    st.metric("Alertas detectadas", len(alertas))
    if alertas.empty:
        st.info("Sin coincidencias con los filtros actuales.")
    else:
        st.dataframe(alertas, width="stretch", hide_index=True)
        st.download_button("Exportar alertas CSV", alertas.to_csv(index=False).encode("utf-8-sig"),
                           file_name="oes_alertas.csv", mime="text/csv")

# ------------------------------------------------------------------ resúmenes asistidos con revisión humana
with tab_r:
    st.warning("El borrador automático **no es un dato verificado**. Solo un revisor humano "
               "puede aprobarlo tras compararlo con la nota original.")
    opciones = {f"#{r.id} · {r.titulo}": int(r.id) for r in df.itertuples()}
    elegido = st.selectbox("Noticia", list(opciones))
    nid = opciones[elegido]
    fila = df[df["id"] == nid].iloc[0]
    st.markdown(f"**Texto registrado:** {fila['resumen']}")
    st.markdown(f"**Fuente:** {fila['url']}")
    if PUEDE_EDITAR and st.button("Generar borrador"):
        oes.generar_borrador(con, nid)
        st.rerun()
    fila = pd.read_sql_query("SELECT * FROM v_noticias WHERE id = ?", con, params=(nid,)).iloc[0]
    st.markdown(f"**Estado del resumen:** `{fila['resumen_ia_estado']}`")
    if fila["resumen_ia"]:
        st.info(fila["resumen_ia"])
    if not PUEDE_EDITAR:
        solo_lectura()
        if fila["resumen_ia_revisor"]:
            st.caption(f"Revisado por: {fila['resumen_ia_revisor']}")
    elif fila["resumen_ia_estado"] == "pendiente_revision":
        revisor = st.text_input("Nombre del revisor", key="revisor")
        a, b = st.columns(2)
        if a.button("Aprobar") and revisor.strip():
            oes.revisar_resumen(con, nid, True, revisor)
            st.rerun()
        if b.button("Rechazar") and revisor.strip():
            oes.revisar_resumen(con, nid, False, revisor)
            st.rerun()
        if not revisor.strip():
            st.caption("Escriba su nombre para poder aprobar o rechazar.")
    elif fila["resumen_ia_revisor"]:
        st.caption(f"Revisado por: {fila['resumen_ia_revisor']}")

# ------------------------------------------------------------------ registro de cambios normativos
with tab_c:
    cambios = pd.read_sql_query(
        "SELECT fecha, norma, entidad, descripcion, url, estado_verificacion "
        "FROM cambios_normativos ORDER BY fecha DESC", con)
    st.dataframe(cambios, width="stretch", hide_index=True)
    if not PUEDE_EDITAR:
        solo_lectura()
    else:
        with st.expander("Registrar cambio normativo"):
            with st.form("form_norma", clear_on_submit=True):
                f_fecha = st.text_input("Fecha (AAAA-MM-DD)")
                f_norma = st.text_input("Norma")
                f_ent = st.text_input("Entidad emisora")
                f_desc = st.text_area("Descripción (redacción propia)")
                f_url = st.text_input("URL directa de la norma")
                if st.form_submit_button("Guardar"):
                    if (all([f_norma.strip(), f_ent.strip(), f_desc.strip()])
                            and oes.validar_fecha(f_fecha) and oes.validar_url(f_url)):
                        try:
                            con.execute("INSERT INTO cambios_normativos (fecha,norma,entidad,descripcion,url) "
                                        "VALUES (?,?,?,?,?)", (f_fecha, f_norma, f_ent, f_desc, f_url))
                            con.commit()
                            st.success("Registrado como pendiente de verificación.")
                        except Exception:
                            st.error("Ya existe una norma con esa URL.")
                    else:
                        st.error("Revise campos, fecha (AAAA-MM-DD) y URL.")

# ------------------------------------------------------------------ transparencia y calidad
with tab_t:
    st.warning("Módulo de **estructura demostrativa**: las cifras cargadas pertenecen a una "
               "institución ficticia. Reemplácelas por datos públicos con URL de origen.")
    ind_df = pd.read_sql_query("SELECT * FROM indicadores_publicos ORDER BY modulo, indicador", con)
    for modulo, titulo in [("transparencia", "Transparencia presupuestal"),
                           ("calidad", "Condiciones de calidad")]:
        st.subheader(titulo)
        sub = ind_df[ind_df["modulo"] == modulo]
        st.dataframe(sub[["institucion", "indicador", "valor", "unidad", "periodo",
                          "fuente_url", "estado_verificacion"]], width="stretch", hide_index=True)
    st.caption("Un conteo de noticias o un indicador aislado no demuestra la calidad de una universidad.")

# ------------------------------------------------------------------ alta de noticia (RF01)
with tab_add:
    if not PUEDE_EDITAR:
        solo_lectura()
    else:
        with st.form("form_noticia", clear_on_submit=True):
            titulo = st.text_input("Título")
            institucion = st.text_input("Institución")
            categoria = st.selectbox("Categoría", oes.CATEGORIAS)
            fuente = st.text_input("Fuente")
            fecha = st.text_input("Fecha de la noticia (AAAA-MM-DD)")
            url = st.text_input("URL directa de la nota")
            resumen = st.text_area("Resumen (redacción propia)")
            verificado_por = st.text_input("Verificado por (opcional)")
            if st.form_submit_button("Guardar"):
                ok, res = oes.registrar_noticia(
                    con, titulo, institucion, categoria, fuente, fecha, url, resumen,
                    verificado_por=verificado_por or None,
                    estado="verificado" if verificado_por.strip() else "pendiente")
                if ok:
                    st.success(f"Noticia #{res} registrada. Actualice la página para verla en la tabla.")
                else:
                    st.error(res)

con.close()
