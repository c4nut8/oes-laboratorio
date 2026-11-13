"""Crea oes.db (esquema normalizado) y carga datos DEMOSTRATIVOS. Se puede ejecutar varias veces."""
import sqlite3

from oes_core import DB

ESQUEMA = """
CREATE TABLE IF NOT EXISTS instituciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fuentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    url TEXT);
CREATE TABLE IF NOT EXISTS noticias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    fecha TEXT NOT NULL,
    categoria TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    resumen TEXT NOT NULL,
    institucion_id INTEGER NOT NULL REFERENCES instituciones(id),
    fuente_id INTEGER NOT NULL REFERENCES fuentes(id),
    fecha_captura TEXT NOT NULL,
    verificado_por TEXT,
    estado_verificacion TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_verificacion IN ('pendiente','verificado','rechazado')),
    resumen_ia TEXT,
    resumen_ia_estado TEXT NOT NULL DEFAULT 'sin_generar'
        CHECK (resumen_ia_estado IN ('sin_generar','pendiente_revision','aprobado','rechazado')),
    resumen_ia_revisor TEXT);
CREATE TABLE IF NOT EXISTS alertas_palabras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    palabra TEXT NOT NULL UNIQUE,
    activa INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS cambios_normativos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    norma TEXT NOT NULL,
    entidad TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    estado_verificacion TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_verificacion IN ('pendiente','verificado','rechazado')));
CREATE TABLE IF NOT EXISTS indicadores_publicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo TEXT NOT NULL CHECK (modulo IN ('transparencia','calidad')),
    institucion TEXT NOT NULL,
    indicador TEXT NOT NULL,
    valor REAL NOT NULL,
    unidad TEXT NOT NULL,
    periodo TEXT NOT NULL,
    fuente_url TEXT,
    estado_verificacion TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_verificacion IN ('pendiente','verificado','rechazado')),
    UNIQUE (modulo, institucion, indicador, periodo));
DROP VIEW IF EXISTS v_noticias;
CREATE VIEW v_noticias AS
SELECT n.id, n.titulo, i.nombre AS institucion, n.categoria, f.nombre AS fuente, n.fecha,
       n.url, n.resumen, n.fecha_captura, n.verificado_por, n.estado_verificacion,
       n.resumen_ia, n.resumen_ia_estado, n.resumen_ia_revisor
FROM noticias n JOIN instituciones i ON i.id = n.institucion_id
JOIN fuentes f ON f.id = n.fuente_id;
"""

# Registros DEMOSTRATIVOS: las URLs apuntan a portales, no a notas concretas.
NOTICIAS = [
    ("Ejemplo: convocatoria de becas", "PRONABEC", "Ente rector", "2026-11-06",
     "https://www.pronabec.gob.pe/",
     "Registro didáctico. Se simula una convocatoria de becas para estudios superiores. "
     "Verificar la nota original antes de citar."),
    ("Ejemplo: actividad de investigación", "UNMSM", "Universidad pública", "2026-11-06",
     "https://www.unmsm.edu.pe/",
     "Registro didáctico. Se simula una actividad de investigación universitaria. "
     "Verificar la noticia original antes de citar."),
    ("Ejemplo: programa académico", "PUCP", "Universidad privada", "2026-11-05",
     "https://www.pucp.edu.pe/",
     "Registro didáctico. Se simula el anuncio de un programa académico. "
     "Verificar la noticia original antes de citar."),
]

PALABRAS = ["licenciamiento", "becas", "investigación", "acreditación", "presupuesto"]

CAMBIOS = [  # DEMOSTRATIVO: reemplazar por normas reales verificadas en El Peruano / SUNEDU
    ("2026-11-04", "Norma de ejemplo N.º 000-2026", "SUNEDU",
     "Registro didáctico de un cambio normativo hipotético sobre licenciamiento.",
     "https://www.gob.pe/sunedu"),
]

INDICADORES = [  # DEMOSTRATIVO con institución ficticia: no son cifras reales
    ("transparencia", "Universidad Ejemplo (ficticia)", "Ejecución presupuestal", 78.5, "%", "2025"),
    ("transparencia", "Universidad Ejemplo (ficticia)", "Presupuesto institucional modificado", 12.4, "millones S/", "2025"),
    ("calidad", "Universidad Ejemplo (ficticia)", "Docentes con doctorado", 14.0, "%", "2025"),
    ("calidad", "Universidad Ejemplo (ficticia)", "Programas acreditados", 3, "programas", "2025"),
]


def main():
    with sqlite3.connect(DB) as con:
        con.executescript(ESQUEMA)
        for nombre, url in [("Portal institucional (ejemplo)", None)]:
            con.execute("INSERT OR IGNORE INTO fuentes (nombre, url) VALUES (?,?)", (nombre, url))
        fuente_id = con.execute("SELECT id FROM fuentes WHERE nombre = 'Portal institucional (ejemplo)'").fetchone()[0]
        for titulo, inst, cat, fecha, url, resumen in NOTICIAS:
            con.execute("INSERT OR IGNORE INTO instituciones (nombre, tipo) VALUES (?,?)", (inst, cat))
            inst_id = con.execute("SELECT id FROM instituciones WHERE nombre = ?", (inst,)).fetchone()[0]
            con.execute("""INSERT OR IGNORE INTO noticias (titulo, fecha, categoria, url, resumen,
                           institucion_id, fuente_id, fecha_captura, estado_verificacion)
                           VALUES (?,?,?,?,?,?,?,?,'pendiente')""",
                        (titulo, fecha, cat, url, resumen, inst_id, fuente_id, "2026-11-12"))
        con.executemany("INSERT OR IGNORE INTO alertas_palabras (palabra) VALUES (?)", [(p,) for p in PALABRAS])
        con.executemany("INSERT OR IGNORE INTO cambios_normativos (fecha,norma,entidad,descripcion,url) VALUES (?,?,?,?,?)", CAMBIOS)
        con.executemany("""INSERT OR IGNORE INTO indicadores_publicos
                           (modulo,institucion,indicador,valor,unidad,periodo) VALUES (?,?,?,?,?,?)""", INDICADORES)
    print("Base creada:", DB)


if __name__ == "__main__":
    main()
