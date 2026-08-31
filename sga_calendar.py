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

def parsear_fecha_cierre(texto):
    try:
        match = re.search(
            r"(\d{1,2})\s+de\s+([a-zA-Z]+)\s+de\s+(\d{4})\s+(\d{1,2}:\d{2})",
            texto,
            re.IGNORECASE
        )
        if match:
            dia = int(match.group(1))
            mes_nombre = match.group(2).lower()
            anio = int(match.group(3))
            hora_str = match.group(4)

            mes = MESES_ES.get(mes_nombre, 1)
            hora, minuto = map(int, hora_str.split(":"))

            if "pm" in texto.lower() and hora < 12:
                hora += 12
            elif "am" in texto.lower() and hora == 12:
                hora = 0

            dt_local = datetime(anio, mes, dia, hora, minuto)
            return TZ_ECUADOR.localize(dt_local)

        match_num = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", texto)
        if match_num:
            dt_local = datetime(
                int(match_num.group(1)),
                int(match_num.group(2)),
                int(match_num.group(3)),
                int(match_num.group(4)),
                int(match_num.group(5))
            )
            return TZ_ECUADOR.localize(dt_local)
    except Exception:
        pass
    return None

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
    return resultado if len(resultado) > 2 else "Evaluación / Tarea Pendiente"

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

    pendientes = []
    filas = soup.find_all("tr")

    # Filtro estricto: solo incluir estados solicitados
    ESTADOS_PERMITIDOS = ["por evaluar", "pendiente", "sin entregar"]

    for i, fila in enumerate(filas):
        texto_fila = fila.text.strip()
        texto_lower = texto_fila.lower()

        if not texto_fila or "cumplimiento de actividades" in texto_lower:
            continue

        # Verificar si la fila contiene exactamente alguno de los estados válidos
        es_valido = any(estado in texto_lower for estado in ESTADOS_PERMITIDOS)

        if es_valido:
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
            fecha_limite = parsear_fecha_cierre(texto_fila)

            if fecha_limite:
                pendientes.append({
                    "materia": materia["nombre"],
                    "titulo": titulo_tarea,
                    "fecha_limite": fecha_limite,
                    "url": materia["url_actividades"]
                })
                print(f"   ↳ ✅ TAREA INCLUIDA: {titulo_tarea} | Cierra: {fecha_limite}")

    return pendientes

def generar_calendario_ics(lista_tareas):
    cal = Calendar()
    for tarea in lista_tareas:
        event = Event()
        event.name = f"[{tarea['materia']}] {tarea['titulo']}"
        event.begin = tarea["fecha_limite"]
        event.description = (
            f"Materia: {tarea['materia']}\n"
            f"Tarea/Evaluación: {tarea['titulo']}\n"
            f"Estado: PENDIENTE / POR EVALUAR / SIN ENTREGAR\n"
            f"Enlace SGA: {tarea['url']}"
        )
        cal.events.add(event)

    with open(OUTPUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"\n🚀 ¡PROCESO COMPLETADO EXITOSAMENTE!")
    print(f"📁 Se generó '{OUTPUT_ICS}' con {len(lista_tareas)} actividad(es) válida(s).")

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

        todas_las_pendientes = []
        for mat in materias:
            tareas = extraer_actividades_de_materia(driver, mat)
            todas_las_pendientes.extend(tareas)

        generar_calendario_ics(todas_las_pendientes)

    except Exception as e:
        print(f"\n❌ Error en la ejecución: {e}")
        raise e
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
