"""Pruebas P1-P6 de la guía + pruebas del nivel avanzado.
Usa una copia temporal de la base: no modifica oes.db. Ejecutar: python pruebas.py"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp()) / "oes_test.db"
os.environ["OES_DB"] = str(TMP)
sys.path.insert(0, str(AQUI))

import pandas as pd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import oes_core as oes  # noqa: E402

resultados = []


def prueba(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion), detalle))
    print(f"[{'OK' if condicion else 'FALLA'}] {nombre} {detalle}")


def cargar():
    with oes.conectar() as con:
        return pd.read_sql_query("SELECT * FROM v_noticias ORDER BY fecha DESC", con)


def preparar():
    subprocess.run([sys.executable, str(AQUI / "preparar_datos.py")], check=True,
                   env=os.environ, capture_output=True)


# P1: ejecutar la carga dos veces no duplica las URLs
preparar(); preparar()
df = cargar()
prueba("P1 carga doble sin duplicados", len(df) == 3 and df["url"].is_unique, f"({len(df)} noticias)")

# P2: filtrar 'Universidad pública' muestra UNMSM
f = oes.filtrar(df, ["Universidad pública"])
prueba("P2 filtro Universidad pública", list(f["institucion"]) == ["UNMSM"], f"-> {list(f['institucion'])}")

# P3: buscar PUCP da una fila
f = oes.filtrar(df, texto="PUCP")
prueba("P3 búsqueda PUCP", len(f) == 1, f"-> {len(f)} fila")

# P4: término inexistente -> 0 noticias, sin error (lógica y pantalla)
f = oes.filtrar(df, texto="zzzz-no-existe")
ind = oes.indicadores(f)
prueba("P4 término inexistente (lógica)", ind["noticias"] == 0 and ind["instituciones"] == 0)
at = AppTest.from_file(str(AQUI / "app.py"), default_timeout=30).run()
prueba("App inicia sin excepciones", not at.exception, f"{[e.value for e in at.exception]}")
metricas = {m.label: m.value for m in at.metric}
prueba("App muestra 3 noticias, 3 instituciones, 3 categorías al iniciar",
       (metricas.get("Noticias"), metricas.get("Instituciones"), metricas.get("Categorías"))
       == ("3", "3", "3"), f"{metricas}")
at.sidebar.text_input[0].set_value("zzzz-no-existe").run()
metricas = {m.label: m.value for m in at.metric if m.label in ("Noticias", "Instituciones")}
prueba("P4 término inexistente (pantalla)", not at.exception and metricas.get("Noticias") == "0"
       and any("No hay resultados" in i.value for i in at.info), f"{metricas}")

# P5: exportar CSV con encabezados y filas filtradas
csv = oes.filtrar(df, texto="PUCP").to_csv(index=False).encode("utf-8-sig")
tmp_csv = TMP.with_name("export.csv"); tmp_csv.write_bytes(csv)
leido = pd.read_csv(tmp_csv, encoding="utf-8-sig")
prueba("P5 exportación CSV", len(leido) == 1 and {"titulo", "url", "fecha"} <= set(leido.columns),
       f"({len(leido)} fila, {len(leido.columns)} columnas)")

# P6: agregar una noticia aumenta el contador y conserva la URL directa
# (en la prueba automática se usa un registro de PRUEBA; en la entrega real use uno verificado)
with oes.conectar() as con:
    ok, nid = oes.registrar_noticia(
        con, "REGISTRO DE PRUEBA automática", "Institución de prueba", "Normativa",
        "Fuente de prueba", "2026-11-12", "https://example.org/nota-directa-prueba",
        "Texto de prueba. Segunda frase. Tercera frase.", verificado_por="Equipo", estado="verificado")
df2 = cargar()
fila = df2[df2["id"] == nid].iloc[0]
prueba("P6 agregar noticia", ok and len(df2) == 4 and fila["url"] == "https://example.org/nota-directa-prueba"
       and fila["estado_verificacion"] == "verificado" and fila["fecha_captura"])

# --- validaciones adicionales
with oes.conectar() as con:
    dup = oes.registrar_noticia(con, "x", "x", "Otra", "x", "2026-11-12",
                                "https://example.org/nota-directa-prueba", "x")
    mala_fecha = oes.registrar_noticia(con, "x", "x", "Otra", "x", "12/11/2026", "https://a.pe/b", "x")
    mala_url = oes.registrar_noticia(con, "x", "x", "Otra", "x", "2026-11-12", "no-es-url", "x")
prueba("Rechaza URL duplicada, fecha y URL inválidas", not dup[0] and not mala_fecha[0] and not mala_url[0])

# filtro por rango de fechas
r = oes.filtrar(df2, desde="2026-11-06", hasta="2026-11-12")
prueba("Filtro por rango de fechas", set(r["institucion"]) == {"PRONABEC", "UNMSM", "Institución de prueba"},
       f"-> {sorted(r['institucion'])}")

# alertas (sin tildes / mayúsculas)
al = oes.detectar_alertas(df2, ["INVESTIGACION", "becas"])
prueba("Alertas por palabra clave", {a["palabra"] for a in al} == {"INVESTIGACION", "becas"} and len(al) == 2, f"-> {len(al)} alertas")

# resumen asistido: borrador -> pendiente; solo aprueba un humano con nombre
with oes.conectar() as con:
    oes.generar_borrador(con, int(nid))
    estado1 = con.execute("SELECT resumen_ia_estado, resumen_ia FROM noticias WHERE id=?", (nid,)).fetchone()
    sin_nombre = oes.revisar_resumen(con, int(nid), True, "  ")
    oes.revisar_resumen(con, int(nid), True, "Revisora 1")
    estado2 = con.execute("SELECT resumen_ia_estado, resumen_ia_revisor FROM noticias WHERE id=?", (nid,)).fetchone()
prueba("Resumen IA: borrador pendiente y aprobación humana registrada",
       estado1[0] == "pendiente_revision" and "borrador" in estado1[1] and not sin_nombre
       and tuple(estado2) == ("aprobado", "Revisora 1"))

# restricciones de la BD
try:
    with oes.conectar() as con:
        con.execute("UPDATE noticias SET estado_verificacion='inventado' WHERE id=1")
    chk = False
except sqlite3.IntegrityError:
    chk = True
prueba("La BD rechaza estados de verificación no válidos", chk)

# la app sigue funcionando con las nuevas pestañas y datos
at = AppTest.from_file(str(AQUI / "app.py"), default_timeout=30).run()
prueba("App con 4 noticias sin errores", not at.exception and {m.label: m.value for m in at.metric}["Noticias"] == "4")

total = len(resultados); ok_n = sum(1 for _, o, _ in resultados if o)
print(f"\nResumen: {ok_n}/{total} pruebas aprobadas")
shutil.rmtree(TMP.parent, ignore_errors=True)
sys.exit(0 if ok_n == total else 1)
