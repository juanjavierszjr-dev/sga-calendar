import os
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from ics import Calendar, Event
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ==============================================================================
# CONFIGURACIÓN DE PARÁMETROS (DESDE SECRETOS DE GITHUB)
# ==============================================================================
USUARIO = os.getenv("SGA_USUARIO", "jsanchezc29")
CONTRASEÑA = os.getenv("SGA_PASS", "Gabito20151388@**")

SGA_URL = "https://sga.uteq.edu.ec/"
OUTPUT_ICS = "mis_tareas_uteq.ics"

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
    time.sleep(3)

def obtener_lista_materias(driver, wait):
    url_materias = f"{SGA_URL}alu_materias"
    print(f"\n➡️  Navegando a la lista de materias: {url_materias}")
    driver.get(url_materias)
    time.sleep(4)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    materias = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "action=" in href and "id=" in href:
            match = re.search(r"id=([A-Za-z0-9]+)", href)
            if match:
                materia_id = match.group(1)
                nombre = a.text.strip() or f"Materia_{materia_id[:5]}"
                url_actividades = f"{SGA_URL}alu_documentos?action=actividades_materia&id={materia_id}"
                if not any(m["id"] == materia_id for m in materias):
                    materias.append({
                        "id": materia_id,
                        "nombre": nombre,
                        "url_actividades": url_actividades
                    })

    if not materias:
        print("🔍 Probando en vista de planificación de clases...")
        driver.get(f"{SGA_URL}alu_documentos?action=planificacionclase")
        time.sleep(4)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            match = re.search(r"id=([A-Za-z0-9]+)", href)
            if match and ("actividades" in href or "planificacion" in href or "materia" in href):
                materia_id = match.group(1)
                nombre = a.text.strip() or f"Materia_{materia_id[:5]}"
                url_actividades = f"{SGA_URL}alu_documentos?action=actividades_materia&id={materia_id}"
                if not any(m["id"] == materia_id for m in materias):
                    materias.append({
                        "id": materia_id,
                        "nombre": nombre,
                        "url_actividades": url_actividades
                    })

    print(f"✅ Se encontraron {len(materias)} materia(s).")
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

            return datetime(anio, mes, dia, hora, minuto)

        match_num = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", texto)
        if match_num:
            return datetime(
                int(match_num.group(1)),
                int(match_num.group(2)),
                int(match_num.group(3)),
                int(match_num.group(4)),
                int(match_num.group(5))
            )
    except Exception:
        pass
    return None

def extraer_actividades_de_materia(driver, materia):
    print(f"\n🔍 Entrando a actividades de: {materia['nombre']}")
    driver.get(materia['url_actividades'])
    time.sleep(3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    pendientes = []

    filas = soup.find_all("tr", class_=re.compile(r"am-fila", re.I))
    if not filas:
        filas = soup.find_all("tr")

    estados_finalizados = ["calificado", "evaluado", "cerrada", "finalizado", "cumplidas", "cumplida"]

    for i, fila in enumerate(filas):
        texto_fila = fila.text.strip()
        texto_lower = texto_fila.lower()

        if not texto_fila or "cumplimiento de actividades" in texto_lower:
            continue

        if any(estado in texto_lower for estado in estados_finalizados):
            continue

        es_pendiente = any(st in texto_lower for st in ["por evaluar", "próximamente", "proximamente", "pendiente", "abierta", "inicio"])
        
        if es_pendiente or not any(st in texto_lower for st in estados_finalizados):
            titulo_elem = fila.find(["a", "h5", "h4", "strong", "b", "span"])
            col_actividad = fila.find(attrs={"data-title": re.compile("Actividad", re.I)}) or fila
            titulo_tarea = col_actividad.text.strip().split("\n")[0] if col_actividad else (titulo_elem.text.strip() if titulo_elem else f"Actividad {i+1}")
            titulo_tarea = re.sub(r"\s+", " ", titulo_tarea)

            fecha_limite = parsear_fecha_cierre(texto_fila)

            if fecha_limite:
                pendientes.append({
                    "materia": materia["nombre"],
                    "titulo": titulo_tarea,
                    "fecha_limite": fecha_limite,
                    "url": materia["url_actividades"]
                })
                print(f"   ↳ ✅ TAREA/EXAMEN PENDIENTE: {titulo_tarea} | Cierra: {fecha_limite}")

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
            f"Estado: PENDIENTE / POR EVALUAR\n"
            f"Enlace SGA: {tarea['url']}"
        )
        cal.events.add(event)

    with open(OUTPUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"\n🚀 ¡PROCESO COMPLETADO EXITOSAMENTE!")
    print(f"📁 Se generó '{OUTPUT_ICS}' con {len(lista_tareas)} actividad(es) pendiente(s)/por evaluar.")

def main():
    options = webdriver.ChromeOptions()
    # MODO HEADLESS PARA SERVIDORES DE GITHUB ACTIONS
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
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
