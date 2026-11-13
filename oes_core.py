"""Funciones compartidas: acceso a la base, alertas, resumenes asistidos y registro de noticias."""
import json
import os
import re
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path

DB = Path(os.environ.get("OES_DB", Path(__file__).with_name("oes.db")))

CATEGORIAS = ["Ente rector", "Universidad pública", "Universidad privada",
              "Normativa", "Calidad", "Otra"]
ESTADOS_VERIF = ["pendiente", "verificado", "rechazado"]


def conectar(db=None):
    con = sqlite3.connect(db or DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _id_por_nombre(con, tabla, nombre, extra=None):
    """Devuelve el id de un registro de instituciones/fuentes; lo crea si no existe."""
    fila = con.execute(f"SELECT id FROM {tabla} WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        return fila[0]
    if tabla == "instituciones":
        cur = con.execute("INSERT INTO instituciones (nombre, tipo) VALUES (?, ?)",
                          (nombre, extra or "Otra"))
    else:
        cur = con.execute("INSERT INTO fuentes (nombre, url) VALUES (?, ?)", (nombre, extra))
    return cur.lastrowid


def validar_url(url):
    return bool(re.match(r"^https?://[^\s/]+\.[^\s/]+", url or ""))


def validar_fecha(texto):
    try:
        date.fromisoformat(texto)
        return True
    except (TypeError, ValueError):
        return False


def registrar_noticia(con, titulo, institucion, categoria, fuente, fecha, url, resumen,
                      fuente_url=None, verificado_por=None, estado="pendiente"):
    """RF01. Devuelve (True, id) o (False, motivo). No duplica URLs."""
    if not all([titulo.strip(), institucion.strip(), fuente.strip(), resumen.strip()]):
        return False, "Todos los campos son obligatorios."
    if not validar_fecha(fecha):
        return False, "La fecha debe tener formato AAAA-MM-DD."
    if not validar_url(url):
        return False, "La URL debe comenzar con http:// o https://."
    if con.execute("SELECT 1 FROM noticias WHERE url = ?", (url,)).fetchone():
        return False, "Ya existe una noticia con esa URL."
    inst_id = _id_por_nombre(con, "instituciones", institucion.strip(), categoria)
    fuente_id = _id_por_nombre(con, "fuentes", fuente.strip(), fuente_url)
    cur = con.execute(
        """INSERT INTO noticias (titulo, fecha, categoria, url, resumen, institucion_id,
           fuente_id, fecha_captura, verificado_por, estado_verificacion)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (titulo.strip(), fecha, categoria, url.strip(), resumen.strip(), inst_id, fuente_id,
         date.today().isoformat(), verificado_por, estado))
    con.commit()
    return True, cur.lastrowid


# ---------------------------------------------------------------- consultas (RF02, RF03)
def filtrar(df, categorias=None, texto="", desde=None, hasta=None, estados=None):
    """Aplica los filtros del tablero sobre un DataFrame de v_noticias."""
    out = df.copy()
    if categorias is not None:
        out = out[out["categoria"].isin(categorias)]
    if estados is not None:
        out = out[out["estado_verificacion"].isin(estados)]
    if desde:
        out = out[out["fecha"] >= str(desde)]
    if hasta:
        out = out[out["fecha"] <= str(hasta)]
    if texto and texto.strip():
        t = texto.strip()
        m = (out["titulo"].str.contains(t, case=False, regex=False)
             | out["institucion"].str.contains(t, case=False, regex=False))
        out = out[m]
    return out


def indicadores(df):
    return {"noticias": len(df),
            "instituciones": int(df["institucion"].nunique()),
            "categorias": int(df["categoria"].nunique()),
            "verificadas": int((df["estado_verificacion"] == "verificado").sum())}


# ---------------------------------------------------------------- alertas por palabras clave
def _normalizar(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s or "").lower()
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def detectar_alertas(df, palabras):
    """Devuelve filas (noticia, palabra) donde la palabra aparece en titulo o resumen.
    Insensible a mayúsculas y tildes. Es coincidencia de texto, no 'inteligencia'."""
    filas = []
    for _, n in df.iterrows():
        texto = _normalizar(f"{n['titulo']} {n['resumen']}")
        for p in palabras:
            if _normalizar(p) and _normalizar(p) in texto:
                filas.append({"fecha": n["fecha"], "institucion": n["institucion"],
                              "titulo": n["titulo"], "palabra": p, "url": n["url"],
                              "estado_verificacion": n["estado_verificacion"]})
    return filas


# ---------------------------------------------------------------- resumen asistido (con revisión humana)
def resumen_borrador(titulo, resumen, max_frases=2):
    """Borrador local y reproducible (extractivo): selecciona las frases con más
    términos relevantes. Si OES_OLLAMA_MODEL está definido, usa un LLM local de Ollama."""
    modelo = os.environ.get("OES_OLLAMA_MODEL")
    if modelo:
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=json.dumps({"model": modelo, "stream": False,
                                 "prompt": ("Resume en máximo 2 frases, sin añadir datos que no "
                                            f"estén en el texto.\nTítulo: {titulo}\nTexto: {resumen}")}
                                ).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["response"].strip() + " [borrador LLM local]"
        except Exception:
            pass  # si Ollama no responde, se usa el método local sencillo
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", resumen.strip()) if f.strip()]
    if len(frases) <= max_frases:
        return " ".join(frases) + " [borrador extractivo]"
    palabras = set(re.findall(r"\w{5,}", _normalizar(titulo)))
    puntaje = [(sum(w in _normalizar(f) for w in palabras), -i, f) for i, f in enumerate(frases)]
    elegidas = sorted(sorted(puntaje, reverse=True)[:max_frases], key=lambda x: -x[1])
    return " ".join(f for _, _, f in elegidas) + " [borrador extractivo]"


def generar_borrador(con, noticia_id):
    n = con.execute("SELECT titulo, resumen FROM noticias WHERE id = ?", (noticia_id,)).fetchone()
    if not n:
        return False
    con.execute("UPDATE noticias SET resumen_ia = ?, resumen_ia_estado = 'pendiente_revision' "
                "WHERE id = ?", (resumen_borrador(n["titulo"], n["resumen"]), noticia_id))
    con.commit()
    return True


def revisar_resumen(con, noticia_id, aprobado, revisor):
    """La IA solo propone; un humano aprueba o rechaza y queda registrado quién."""
    if not revisor.strip():
        return False
    con.execute("UPDATE noticias SET resumen_ia_estado = ?, resumen_ia_revisor = ? WHERE id = ? "
                "AND resumen_ia_estado = 'pendiente_revision'",
                ("aprobado" if aprobado else "rechazado", revisor.strip(), noticia_id))
    con.commit()
    return True
