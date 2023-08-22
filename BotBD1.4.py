import random
import re
import sqlite3
import time
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler, Updater
import telegram
import logging
import asyncio
import aiohttp
import aiosqlite
import spacy

#Carga del model en español de spacy para la categorización 
nlp = spacy.load("es_core_news_sm")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#Versión de python
print(telegram.__version__)

# Mantén este valor secreto
token = '6302321641:AAHgQuqA62sGofOLwrHFvmP2FPm29B2jf6c'  

async def fetch(url, session):
    async with session.get(url) as response:
        return await response.text()

def create_table():
    with sqlite3.connect('productos.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            nombre TEXT PRIMARY KEY,
            oferta TEXT,
            precio_anterior TEXT,
            enlace TEXT
                  
        )
        ''')
        conn.commit()  # Confirmación explícita

def add_data_category_column():
    with sqlite3.connect('productos.db') as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE productos ADD COLUMN data_category TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                pass  # La columna ya existe, no hacer nada.
            else:
                raise  # Otro error ocurrió, debes manejarlo o dejar que el programa falle.
       

def add_category_column():
    with sqlite3.connect('productos.db') as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE productos ADD COLUMN categoria TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                pass  # La columna ya existe, no hacer nada.
            else:
                raise  # Otro error ocurrió, debes manejarlo o dejar que el programa falle.

def add_discount_percentage_column():
    with sqlite3.connect('productos.db') as conn:
        cursor = conn.cursor()
        if not column_exists('productos', 'discount_percentage'):
            try:
                cursor.execute('''
                ALTER TABLE productos ADD COLUMN discount_percentage TEXT
                ''')
            except sqlite3.Error as e:
                print(f"Error al añadir la columna discount_percentage: {e}")



def column_exists(table_name, column_name):
    conn = sqlite3.connect('productos.db')
    cursor = conn.cursor()

    # Interpolación segura del nombre de la tabla
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    for column in columns:
        if column[1] == column_name:
            return True

    return False


def get_unique_categories():
    with sqlite3.connect('productos.db') as conn:
        print("Conectado a la base de datos")  # <-- Añade esta línea para depuración
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT categoria FROM productos")
        categories = [row[0] for row in cursor.fetchall()]
        #print("Categorias extraidas:", categories) depuracion
        return categories


def build_category_keyboard(categories):
    keyboard = [[InlineKeyboardButton(category, callback_data=category)] for category in categories]
    #print("Teclado construido:", keyboard)  # <-- Añade esta línea para depuración
    return InlineKeyboardMarkup(keyboard)

def get_products_by_category(category):
    with sqlite3.connect('productos.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM productos WHERE categoria = ?", (category,))
        return cursor.fetchall()

import spacy

# Carga el modelo en español de spaCy
nlp = spacy.load("es_core_news_sm")

async def get_elements(soup):
    # Buscar clases que comienzan con "jsx"
    jsx_elements = soup.find_all(class_=lambda x: x and x.startswith("jsx"))
    
    # Buscar elementos con clases específicas
    pod_link_elements = soup.find_all(class_="jsx-1833870204 jsx-3831830274 pod-link")
    grid_view_elements = soup.find_all(class_="jsx-2907167179 layout_grid-view layout_view_4_GRID")

    return jsx_elements + pod_link_elements + grid_view_elements


def clean_price(price_str):
    logging.info(f"Original price_str: {price_str}")
    
    # Si encontramos un rango (detectado por el signo "-"), tomamos el primer precio
    if '-' in price_str:
        price_str = price_str.split('-')[0].strip()
    
    # Limpiamos la cadena eliminando caracteres no deseados, excepto el punto y dígitos
    cleaned_price = re.sub(r"[^\d\.]", "", price_str.strip())
    
    # Convertimos el precio limpio en un número entero (eliminamos puntos de mil)
    num_price = int(cleaned_price.replace(".", ""))
    
    # Formateamos el número como una cadena con separadores de miles y el signo del peso al principio
    return f"${num_price:,.0f}".replace(",", ".")


def find_element_by_classes(element, tag, classes_to_search):
    """Encuentra el primer elemento que coincide con una de las clases proporcionadas."""
    for class_name in classes_to_search:
        found_element = element.find(tag, class_=class_name)
        if found_element:
            return found_element
    return None


async def get_offers():
    url_base = "https://www.falabella.com/falabella-cl/collection/ofertas"
    new_products = []  # Lista para guardar los nuevos productos encontrados

    async with aiohttp.ClientSession() as session:
        for page in range(1, 15):
            url = f"{url_base}?page={page}"
            
            try:
                async with session.get(url) as response:
                    response.raise_for_status()  # Esto generará un error si el código de estado no es 200
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    all_elements = await get_elements(soup)

                async with aiosqlite.connect('productos.db') as conn:
                    cursor = await conn.cursor()
                     
                    for element in all_elements:
                        product_name = element.find("b", class_="jsx-1833870204 copy2 primary jsx-2889528833 normal pod-subTitle subTitle-rebrand")
                        # Definimos las clases que deseamos busca
                        classes_to_search = ["copy10 primary high jsx-2889528833 normal line-height-22","copy10 primary medium jsx-2889528833 normal line-height-22"]
                        # Buscamos el elemento que tenga alguna de las clases definidas
                        offer = find_element_by_classes(element, None, classes_to_search)
                        discount_badge = element.find("div", class_="jsx-2575670149 discount-badge")
                        # Definimos las clases que deseamos buscar para el precio anterior
                        classes_to_search_price = ["copy3 septenary medium jsx-2889528833 normal crossed line-height-17","copy3 primary medium jsx-2889528833 normal crossed line-height-17", "copy10 primary medium jsx-2889528833 normal line-height-22"]
                        previous_price_element = find_element_by_classes(element, "span", classes_to_search_price)
                        
                        product_in_db = None
                        product_name_text = None
                        current_offer = None

                        # Extraer el porcentaje de descuento
                        discount_percentage = discount_badge.text.strip() if discount_badge else "N/A"
                       
                        if product_name and offer and discount_badge:
                            div_element = element.find("div", class_="jsx-1833870204 jsx-3831830274 pod pod-4_GRID")
                            data_category = div_element["data-category"] if div_element and "data-category" in div_element.attrs else None

                            link_element = element.find("a", class_="jsx-2907167179 layout_grid-view layout_view_4_GRID")
                            link = link_element["href"] if link_element else None
                            logging.info(f"Enlace para {product_name_text}: {link}")

                            product_name_text = product_name.text.strip().split("$")[0].strip()
                            logging.info(f"Descuento para {product_name_text}: {discount_percentage}")

                            if previous_price_element:
                            # Usa una expresión regular para extraer el precio
                                match = re.search(r"\$\s*([\d\.]+)", previous_price_element.text.strip())
                                if match:
                                    raw_previous_price = match.group(1)
                                    logging.info(f"Precio anterior sin limpiar para {product_name_text}: {raw_previous_price}")
                                    previous_price = clean_price(raw_previous_price)
                                    logging.info(f"Precio anterior limpio para {product_name_text}: {previous_price}")
                                else:
                                    previous_price = None

                            logging.info(f"Procesando producto: {product_name_text}")
                            current_offer = clean_price(offer.text.strip())
                            logging.info(f"Oferta actual para {product_name_text}: {current_offer}")

                            if product_name_text:
                                category = assign_category(product_name_text)
                            else:
                                category = "OTROS NEGOCIOS"  # o cualquier valor por defecto

                            if product_name_text:
                                await cursor.execute("SELECT * FROM productos WHERE nombre = ?", (product_name_text,))
                                product_in_db = await cursor.fetchone()

                                if not product_in_db:
                                
                                    try:
                                        await cursor.execute("INSERT OR IGNORE INTO productos VALUES (?, ?, ?, ?, ?, ?, ?)", (product_name_text, current_offer, previous_price, link, data_category, category, discount_percentage))
                                        await conn.commit()
                                        logging.info(f"Producto {product_name_text} agregado a la base de datos.")
                                        new_products.append((product_name_text, current_offer, previous_price, link, data_category, category, discount_percentage))
                                    except sqlite3.Error as e:
                                        logging.error(f"Error al agregar el producto '{product_name_text}' a la base de datos: {e}. Enlace: {link}")
                                    except Exception as e:
                                        logging.error(f"Error inesperado al agregar el producto '{product_name_text}' a la base de datos: {e}. Enlace: {link}")
                                else:
                                    logging.error(f"El producto '{product_name_text}' ya existe en la base de datos. Enlace: {link}")
                                    logging.info(f"Producto {product_name_text} procesado.")
                            else:    
                                logging.error(f"Producto inválido detectado. Enlace: {link}")


            except aiohttp.ClientResponseError as e:
                logging.error(f"Error {e.status}. Pausando durante 60 segundos antes de reintentar.")
                await asyncio.sleep(60)
                continue  # Esto hará que el bucle vuelva al inicio y reintente la misma página

    return new_products  # Devolvemos solo los nuevos productos

categorizar_con_spacy = {
    "MUEBLES": ["Juego Comedor","Juego de Comedor", "Mesa de Centro", "Mesa de Comedor", "Sofá"],
    "MUJER": ["mujer", "jeans mujer","polera mujer", "zatos mujer"],
    "HOMBRE": ["hombre", "camisa formal","polera hombre", "pantalón de vestir", "zapato deportivo", "zapatilla hombre"],
    "DORMITORIO": ["Almohada Soft", "Almohada", "cama", "plumon", "sabanas", "Cama Europea"], 
    "DECOHOGAR": ["Alfombra", "cuadros", "reloj pared"], 
    "ESPECIALES": ["artículo de colección limitada"], 
    "NIÑOS Y JUGUETERÍA": ["Peluches", "peluche"], 
    "DEPORTES Y AIRE LIBRE": ["pelota", "raqueta", "paleta", "pelota", "ping pong", "tenis", "futbol"], 
    "MUNDO BEBÉ": ["Bebesit", "coche", "ropa de bebé", "biberón", "chupete", "mamadera", "leche"], 
    "TECNOLOGÍA": ["Smarwatch", "smartband", "parlante", "audifonos", "iPhone", "celular ", "Notebook", "PC de escritorio", "tablet", "pc", "teclado"], 
    "BELLEZA, HIGIENE Y SALUD": ["Perfume", "pinta labios", "mascarilla", "mascara de pestaña", "maquillaje"], 
    "ORGANIZACIÓN": ["estantería", "cajas organizadoras", "organizador"], 
    "FERRETERÍA Y CONSTRUCCIÓN": ["taladro", "cerrucho" , "herramienta"], 
    "JARDÍN Y TERRAZA": ["plantas", "terraza", "manguera", "planta", "hierbas"], 
    "COCINA Y BAÑO": ["sartén", "taza de baño", "ollas", "Bowl"], 
    "ELECTROHOGAR": ["Horno", "refrigerador", "Microondas ", "Aspiradora "], 
    "MASCOTAS": ["alimento balanceado para gatos", "juguetes interactivos para perros"], 
    "LIBRERÍA Y CELEBRACIONES": ["set de lápices de colores", "decoraciones para fiestas temáticas"], 
    "SERVICIOS E INTANGIBLES": ["suscripción anual de software", "tarjeta de regalo"], 
    "ASEO Y LIMPIEZA": ["limpiador multiuso desinfectante", "trapos de microfibra"], 
    "MALETERÍA Y VIAJES": ["maleta resistente con ruedas", "mochila ergonómica para excursionismo"], 
    "PASATIEMPOS": ["kit para tejer", "rompecabezas de 1000 piezas"], 
    "AUTOMOTRIZ": ["aceite sintético para motores", "cubiertas para asientos"], 
    "INSTRUMENTOS MUSICALES": ["guitarra", "teclado electrónico ", "flauta", "bateria"], 
    "ALIMENTOS Y BEBIDAS": ["vinos de bodegas reconocidas", "quesos artesanales curados"], 
    "OTROS NEGOCIOS": []
}

def assign_category(product_name_text):
    # Paso 1: Enfoque basado en reglas
    for category, keywords in categorizar_con_spacy.items():
        for keyword in keywords:
            if keyword.lower() in product_name_text.lower():
                return category  # Si se encuentra una coincidencia, retorna la categoría

    # Paso 2: Enfoque basado en similitud (si el enfoque basado en reglas no encuentra una coincidencia)
    product_doc = nlp(product_name_text)
    
    best_similarity = 1
    best_category = "OTROS NEGOCIOS"
    
    for category, descriptions in categorizar_con_spacy.items():
        for description in descriptions:
            description_doc = nlp(description)
            similarity = product_doc.similarity(description_doc)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_category = category

    return best_category

def obtener_ofertas():
    """Esta función se encargará de obtener las ofertas."""
    product_offers_links = get_offers()
    return product_offers_links

async def enviar_mensajes_telegram(update, context, product_offers_links):
    """Esta función se encargará de enviar los mensajes a través de Telegram."""
    chat_id = update.effective_chat.id

    # Si encontramos productos
    if product_offers_links:
        # Divide la lista de productos en grupos de 5
        n = 5
        chunks = [product_offers_links[i:i + n] for i in range(0, len(product_offers_links), n)]
        
        for chunk in chunks:
            for product, offer, previous_price, link, data_category, category, discount_percentage  in chunk:
                # Enviamos el nombre del producto, la oferta, el porcentaje de descuento, el precio anterior y el enlace al chat del usuario
                message = f"Producto: {product}\nOferta actual: {offer}\nDescuento: {discount_percentage}\nPrecio anterior: {previous_price}\nEnlace: {link}"
                try:
                    context.bot.send_message(chat_id, message)
                except Exception as e:
                    logging.error(f"Error al enviar el mensaje a través de Telegram: {e}")

            # Espera 2 minutos antes de enviar el siguiente grupo
            await asyncio.sleep(120)
        
        # Mostramos un mensaje al usuario indicando que la búsqueda ha finalizado
        context.bot.send_message(chat_id, "Búsqueda de ofertas completada.")
    else:
        context.bot.send_message(chat_id, "Lo siento, no se pudieron obtener las ofertas en este momento.")


async def asincrono_buscar_ofertas(update, context):
    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id, "Buscando ofertas y actualizando la base de datos, por favor espera...")

    # Espera a que se complete get_offers antes de continuar
    await get_offers()  # No necesitamos el resultado directamente, solo queremos que se actualice la base de datos

    # Informar al usuario que la actualización ha terminado
    context.bot.send_message(chat_id, "Base de datos actualizada con las últimas ofertas.")

     # Mostrar las categorías al usuario
    categories = get_unique_categories()
    keyboard = build_category_keyboard(categories)
    context.bot.send_message(chat_id, "Por favor, selecciona una categoría:", reply_markup=keyboard)
    

def buscar_ofertas(update, context):
    # Crea un nuevo bucle de eventos
    loop = asyncio.new_event_loop()
    
    # Establece este bucle como el bucle de eventos actual
    asyncio.set_event_loop(loop)
    
    # Usa este bucle para ejecutar tu corutina
    loop.run_until_complete(asincrono_buscar_ofertas(update, context))


def category_callback(update, context):
    chat_id = update.effective_chat.id
    query = update.callback_query
    category_selected = query.data
    products = get_products_by_category(category_selected)

    messages = []
    for product in products:
        product_name, offer, previous_price, discount_percentage, data_category, category, link = product
        message = f"Producto: {product_name}\nOferta actual: {offer}\nDescuento: {discount_percentage}\nPrecio anterior: {previous_price}\nEnlace: {link}"
        messages.append(message)

    # Enviar todos los productos en un solo mensaje (puedes dividirlos si es necesario)
    send_offer_messages(context.bot, update.effective_chat.id, messages)

    # Aquí es donde reenvías el teclado con categorías
    categories = get_unique_categories()
    keyboard = build_category_keyboard(categories)
    context.bot.send_message(chat_id, "Selecciona otra categoría si quieres seguir viendo ofertas:", reply_markup=keyboard)
    
    query.answer()

    

def send_offer_messages(bot, chat_id, messages, delay=0.5):
    for message in messages:
        bot.send_message(chat_id, message)
        time.sleep(delay)

def periodic_task(context):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(get_offers())


def main():
    updater = Updater(token, use_context=True)

    dp = updater.dispatcher
    
    dp.add_handler(CallbackQueryHandler(category_callback))
    dp.add_handler(CommandHandler('buscar_ofertas', buscar_ofertas))

    # Agrega la tarea periódica
    job_queue = updater.job_queue
    job_queue.run_repeating(periodic_task, interval=600)  # 600 segundos = 10 minutos

    max_retries = 3
    for i in range(max_retries):
        try:
            updater.start_polling(timeout=300)
            break  # Si la conexión es exitosa, salimos del bucle.
        except telegram.error.TimedOut:
            wait_time = (i + 1) * 10  # Aumentamos el tiempo de espera con cada intento.
            print(f"La solicitud a la API de Telegram se ha demorado demasiado. Reintentando en {wait_time} segundos...")
            time.sleep(wait_time)
        except Exception as e:  # Manejar cualquier otra excepción.
            print(f"Error: {e}. Reintentando en 10 segundos...")
            time.sleep(10)

    updater.idle()

if __name__ == "__main__":
    # Llama a estas funciones al inicio de tu script para asegurarte de que la tabla exista
    create_table()
    add_data_category_column()
    add_category_column()
    add_discount_percentage_column()
    main()
    #loop = asyncio.get_event_loop()
    #new_products = loop.run_until_complete(get_offers())
   
