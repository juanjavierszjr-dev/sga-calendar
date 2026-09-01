import os
import re
import time
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from ics import Calendar, Event
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ==============================================================================
# CONFIGURACIÓN DE PARÁMETROS
# ==============================================================================
USUARIO = os.getenv("SGA_USUARIO", "jsanchezc29")
CONTRASEÑA = os.getenv("SGA_PASS", "Gabito20151388@**")

SGA_URL = "https://sga.uteq.edu.ec/"
OUTPUT_ICS = "mis_tareas_uteq.ics"
TZ_ECUADOR = pytz.timezone("America/Guayaquil")

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

def login_sga(driver, wait):
    print("➡️  Accediendo al SGA UTEQ...")
    driver.get(SGA_URL)

    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "userdeclaracion")))
    usuario_input.clear()
    usuario_input.send_keys(USUARIO)

    pass_input = driver.find_element(By.ID, "passdeclaracion")
    pass_input.clear()
    pass_input.send_keys(CONTRASEÑA)

    driver.find_element(By.ID, "logindeclaracion").click()
    print("✅ Credenciales enviadas. Aceptando declaración...")

    checkbox = wait.until(EC.element_to_be_clickable((By.ID, "acepto")))
    checkbox.click()

    driver.find_element(By.ID, "logindeclaracion1").click()
    print("✅ Login completado.")
    time.sleep(4)

def obtener_lista_materias(driver, wait):
    url_materias = f"{SGA_URL}alu_materias"
    print(f"\n➡️  Navegando a la lista de materias: {url_materias}")
    driver.get(url_materias)
    
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(5)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    materias = []

    cards = soup.find_all("div", class_=re.compile(r"av-card", re.I))

    for card in cards:
        title_elem = card.find(class_=re.compile(r"av-card-title", re.I))
        nombre = title_elem.text.strip() if title_elem else ""

        materia_id = None
        html_card = str(card)

        match_id = re.search(r'id=["\'](?:encabezado_)?([A-Za-z0-9_-]+)["\']', html_card)
        if match_id:
            materia_id = match_id.group(1).replace("encabezado_", "")
        
        if not materia_id:
            match_href = re.search(r'id=([A-Za-z0-9_-]+)', html_card)
            if match_href:
                materia_id = match_href.group(1)

        if materia_id and not any(m["id"] == materia_id for m in materias):
            nombre_final = re.sub(r"\s+", " ", nombre) if nombre else f"Materia_{materia_id[:6]}"
            url_actividades = f"{SGA_URL}alu_documentos?action=actividades_materia&id={materia_id}"
            materias.append({
                "id": materia_id,
                "nombre": nombre_final,
                "url_actividades": url_actividades
            })

    if not materias:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "id=" in href:
                match = re.search(r"id=([A-Za-z0-9_-]+)", href)
                if match:
                    materia_id = match.group(1)
                    url_actividades = f"{SGA_URL}alu_documentos?action=actividades_materia&id={materia_id}"
                    if not any(m["id"] == materia_id for m in materias):
                        materias.append({
                            "id": materia_id,
                            "nombre": f"Materia_{materia_id[:6]}",
                            "url_actividades": url_actividades
                        })

    print(f"\n✅ Total de materias procesadas ({len(materias)}):")
    for m in materias:
        print(f"   📌 {m['nombre']} | ID: {m['id']}")

    return materias

def parsear_fechas_rango(texto):
    """Extrae la fecha de Inicio y Cierre de la fila."""
    fechas = re.findall(
        r"(\d{1,2})\s+de\s+([a-zA-Z]+)\s+de\s+(\d{4})\s+(\d{1,2}:\d{2})\s*(AM|PM|am|pm)?",
        texto,
        re.IGNORECASE
    )
    
    fechas_dt = []
    for f in fechas:
        dia, mes_nombre, anio, hora_str, ampm = f
        mes = MESES_ES.get(mes_nombre.lower(), 1)
        hora, minuto = map(int, hora_str.split(":"))

        if ampm:
            ampm_upper = ampm.upper()
            if ampm_upper == "PM" and hora < 12:
                hora += 12
            elif ampm_upper == "AM" and hora == 12:
                hora = 0

        dt_local = datetime(int(anio), mes, int(dia), hora, minuto)
        fechas_dt.append(TZ_ECUADOR.localize(dt_local))

    if len(fechas_dt) >= 2:
        return fechas_dt[0], fechas_dt[1]
    elif len(fechas_dt) == 1:
        return fechas_dt[0], fechas_dt[0]
    
    return None, None

def limpiar_titulo_tarea(texto):
    patrones_limpieza = [
        r"Inicio\s+\d{1,2}\s+de\s+[a-zA-Z]+\s+de\s+\d{4}.*",
        r"Cierre\s+\d{1,2}\s+de\s+[a-zA-Z]+\s+de\s+\d{4}.*",
        r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?",
        r"↓", r"↑"
    ]
    resultado = texto
    for pat in patrones_limpieza:
        resultado = re.sub(pat, "", resultado, flags=re.IGNORECASE)
    resultado = re.sub(r"\s+", " ", resultado).strip()
    return resultado if len(resultado) > 2 else "Evaluación / Tarea"

def determinar_estado_emoji(texto_lower):
    """Asigna icono y etiqueta según el estado de la tarea en el SGA."""
    # Lista ampliada de palabras clave para tareas completadas o calificadas
    palabras_completado = [
        "calificado", "calificada", "evaluado", "evaluada", 
        "finalizado", "finalizada", "cumplidas", "cumplida", "cerrada"
    ]
    
   def determinar_estado_emoji(texto_lower):
    """Asigna icono y etiqueta según el estado de la tarea en el SGA."""
    
    # 1. Prioridad para tareas pendientes o sin entregar (incluso si dicen 'cerrada')
    palabras_pendiente = ["sin entregar", "pendiente", "abierta", "próximamente", "proximamente"]
    if any(st in texto_lower for st in palabras_pendiente):
        return "🔴", "PENDIENTE / SIN ENTREGAR"
        
    # 2. Tareas entregadas a la espera de calificación
    elif "por evaluar" in texto_lower:
        return "🟡", "POR EVALUAR"
        
    # 3. Tareas completadas o evaluadas (se removió 'cerrada' para evitar falsos positivos)
    elif any(st in texto_lower for st in ["calificado", "calificada", "evaluado", "evaluada", "finalizado", "finalizada", "cumplidas", "cumplida"]):
        return "🟢", "COMPLETADO / EVALUADO"
        
    else:
        return "⚪", "INFORMACIÓN / SIN ESTATUS"

def extraer_actividades_de_materia(driver, materia):
    driver.get(materia['url_actividades'])
    time.sleep(3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    if materia['nombre'].startswith("Materia_"):
        header_meta = soup.find("div", class_="alu-header-meta")
        if header_meta:
            icon_book = header_meta.find("i", class_=re.compile(r"fa-book", re.I))
            if icon_book and icon_book.parent:
                nombre_extraido = icon_book.parent.text.strip()
            else:
                nombre_extraido = header_meta.text.strip()

            nombre_extraido = re.sub(r"\s+", " ", nombre_extraido)
            if len(nombre_extraido) > 2:
                materia['nombre'] = nombre_extraido

    print(f"\n🔍 Entrando a actividades: {materia['nombre']}")

    actividades = []
    filas = soup.find_all("tr")

    for i, fila in enumerate(filas):
        texto_fila = fila.text.strip()
        texto_lower = texto_fila.lower()

        if not texto_fila or "cumplimiento de actividades" in texto_lower:
            continue

        cols = fila.find_all("td")
        titulo_raw = ""
        if cols:
            for col in cols:
                txt = col.text.strip()
                if txt and not txt.lower().startswith("inicio") and not re.search(r"\d{4}", txt):
                    titulo_raw = txt
                    break
            if not titulo_raw:
                titulo_raw = cols[0].text.strip()
        else:
            titulo_elem = fila.find(["a", "strong", "b", "h5", "h4"])
            titulo_raw = titulo_elem.text.strip() if titulo_elem else f"Actividad {i+1}"

        titulo_tarea = limpiar_titulo_tarea(titulo_raw)
        fecha_inicio, fecha_cierre = parsear_fechas_rango(texto_fila)
        emoji, estado_str = determinar_estado_emoji(texto_lower)

        if fecha_inicio and fecha_cierre:
            actividades.append({
                "materia": materia["nombre"],
                "titulo": titulo_tarea,
                "fecha_inicio": fecha_inicio,
                "fecha_cierre": fecha_cierre,
                "emoji": emoji,
                "estado_str": estado_str,
                "url": materia["url_actividades"]
            })
            print(f"   ↳ {emoji} [{estado_str}] {titulo_tarea} | {fecha_inicio.strftime('%d/%m %H:%M')} ➔ {fecha_cierre.strftime('%d/%m %H:%M')}")

    return actividades

def generar_calendario_ics(lista_tareas):
    cal = Calendar()
    for tarea in lista_tareas:
        event = Event()
        # Nombre del evento formateado con emoji de estado
        event.name = f"{tarea['emoji']} [{tarea['materia']}] {tarea['titulo']}"
        
        # Asignación del rango de tiempo (Inicio y Fin)
        event.begin = tarea["fecha_inicio"]
        event.end = tarea["fecha_cierre"]
        
        event.description = (
            f"📌 Materia: {tarea['materia']}\n"
            f"📝 Tarea/Evaluación: {tarea['titulo']}\n"
            f"🏷️ Estado: {tarea['estado_str']}\n"
            f"🚀 Apertura: {tarea['fecha_inicio'].strftime('%d/%m/%Y %H:%M')}\n"
            f"⏰ Cierre: {tarea['fecha_cierre'].strftime('%d/%m/%Y %H:%M')}\n"
            f"🔗 Enlace SGA: {tarea['url']}"
        )
        cal.events.add(event)

    with open(OUTPUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"\n🚀 ¡PROCESO COMPLETADO EXITOSAMENTE!")
    print(f"📁 Se generó '{OUTPUT_ICS}' con {len(lista_tareas)} actividad(es) registradas.")

def main():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)

    try:
        login_sga(driver, wait)
        materias = obtener_lista_materias(driver, wait)

        todas_las_actividades = []
        for mat in materias:
            actividades = extraer_actividades_de_materia(driver, mat)
            todas_las_actividades.extend(actividades)

        generar_calendario_ics(todas_las_actividades)

    except Exception as e:
        print(f"\n❌ Error en la ejecución: {e}")
        raise e
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
