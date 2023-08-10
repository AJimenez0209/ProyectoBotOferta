import sqlite3
import requests
from bs4 import BeautifulSoup
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Bot, Update
import telegram
import re
import time
import random
print(telegram.__version__)


token = '6302321641:AAHgQuqA62sGofOLwrHFvmP2FPm29B2jf6c'  # Reemplaza 'TU_TOKEN_AQUI' con tu token real


def create_table():
    conn = sqlite3.connect('productos.db')
    cursor = conn.cursor()
    
    # Crear la tabla si no existe
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS productos (
        nombre TEXT PRIMARY KEY,
        oferta TEXT,
        precio_anterior TEXT,
        enlace TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def column_exists(table_name, column_name):
    conn = sqlite3.connect('productos.db')
    cursor = conn.cursor()

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    for column in columns:
        if column[1] == column_name:
            return True

    return False


def add_discount_percentage_column():
    conn = sqlite3.connect('productos.db')
    cursor = conn.cursor()

    if not column_exists('productos', 'discount_percentage'):
        try:
            cursor.execute('''
            ALTER TABLE productos ADD COLUMN discount_percentage TEXT
            ''')
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error al añadir la columna discount_percentage: {e}")
        finally:
            conn.close()



# Llama a esta función al inicio de tu script para asegurarte de que la tabla exista
create_table()
add_discount_percentage_column()

def get_elements(soup):
    # Buscar clases que comienzan con "jsx"
    jsx_elements = soup.find_all(class_=lambda x: x and x.startswith("jsx"))
    
    # Buscar elementos con clases específicas
    pod_link_elements = soup.find_all(class_="jsx-1833870204 jsx-3831830274 pod-link")
    grid_view_elements = soup.find_all(class_="jsx-2907167179 layout_grid-view layout_view_4_GRID")

    # Combina todos los elementos encontrados en una lista
    all_elements = jsx_elements + pod_link_elements + grid_view_elements
    
    return all_elements


def clean_price(price_str):
    # Limpiamos la cadena eliminando espacios innecesarios y caracteres no deseados, excepto el punto y el signo del peso
    cleaned_price = re.sub(r"[^\d\.]", "", price_str.strip())
    
    # Convertimos el precio limpio en un número entero (eliminamos puntos de mil)
    num_price = int(cleaned_price.replace(".", ""))
    
    # Formateamos el número como una cadena con separadores de miles y el signo del peso al principio
    formatted_price = f"${num_price:,.0f}".replace(",", ".")
    
    return formatted_price





def get_offers():
    conn = sqlite3.connect('productos.db')
    cursor = conn.cursor()

    url_base = "https://www.falabella.com/falabella-cl/collection/ofertas"
    new_products = []  # Lista para guardar los nuevos productos encontrados

    for page in range(1, 3):
        url = f"{url_base}?page={page}"
        response = requests.get(url)
        sleep_time = random.uniform(3, 7)  # Pausa durante un tiempo aleatorio entre 3 y 7 segundos
        time.sleep(sleep_time)


        soup = BeautifulSoup(response.text, "html.parser")
        all_elements = get_elements(soup)

        if response.status_code != 200:
            print(f"Error {response.status_code}. Pausando durante 60 segundos antes de reintentar.")
            time.sleep(60)
            continue   #Esto hará que el bucle vuelva al inicio y reintente la misma página
        

        for element in all_elements:
            product_name = element.find("b", class_="jsx-1833870204 copy2 primary jsx-2889528833 normal pod-subTitle subTitle-rebrand")
            # Definimos las clases que deseamos buscar
            classes_to_search = [
            "copy10 primary high jsx-2889528833 normal line-height-22",
            "copy10 primary medium jsx-2889528833 normal line-height-22"
            ]
            # Buscamos el elemento que tenga alguna de las clases definidas
            offer = None
            for class_name in classes_to_search:
                offer = element.find(class_=class_name)
                if offer:  # Si encontramos un elemento que coincide, salimos del bucle
                    break

            discount_badge = element.find("div", class_="jsx-2575670149 discount-badge")
            # Definimos las clases que deseamos buscar
            # Definimos las clases que deseamos buscar
            classes_to_search = [
            "copy3 septenary medium jsx-2889528833 normal crossed line-height-17",
            "copy3 primary medium jsx-2889528833 normal crossed line-height-17"
            ]

            # Buscamos el elemento que tenga alguna de las clases definidas
            previous_price_element = None
            for class_name in classes_to_search:
                previous_price_element = element.find("span", class_=class_name)
                if previous_price_element:  # Si encontramos un elemento que coincide, salimos del bucle
                    break
            previous_price = clean_price(previous_price_element.text.strip()) if previous_price_element else None

            # Extraer el porcentaje de descuento
            discount_percentage = discount_badge.text.strip() if discount_badge else "N/A"


            if product_name and offer and discount_badge:
        
                link_element = element.find("a", class_="jsx-2907167179 layout_grid-view layout_view_4_GRID")
                link = link_element["href"] if link_element else None

                product_name_text = product_name.text.strip().split("$")[0].strip()
                current_offer = clean_price(offer.text.strip())

                cursor.execute("SELECT * FROM productos WHERE nombre = ?", (product_name_text,))
                product_in_db = cursor.fetchone()

                # Mostrar el porcentaje de descuento junto con los otros detalles
                print(f"Producto detectado: {product_name_text}, Oferta: {current_offer}, Precio anterior: {previous_price}, Descuento: {discount_percentage}, Enlace: {link}")

                # Definimos last_price antes de la condición if
                last_price = clean_price(product_in_db[3]) if product_in_db and product_in_db[3] else None

                if not product_in_db:
                    try:
                        cursor.execute("INSERT INTO productos VALUES (?, ?, ?, ?, ?)", (product_name_text, current_offer, previous_price, discount_percentage, link))
                        conn.commit()  # Asegúrate de hacer commit después de insertar.
                        print(f"Producto {product_name_text} agregado a la base de datos.")
                        new_products.append((product_name_text, current_offer, previous_price, discount_percentage, link))
                    except sqlite3.Error as e:
                        print(f"Error al agregar el producto {product_name_text} a la base de datos: {e}")

    conn.close()
    return new_products  # Devolvemos solo los nuevos productos


def buscar_ofertas(update, context):
    chat_id = update.effective_chat.id

    product_offers_links = get_offers()
    if product_offers_links:
        for product, offer, previous_price, discount_percentage, link in product_offers_links:
            # Enviamos el nombre del producto, la oferta, el porcentaje de descuento, el precio anterior y el enlace al chat del usuario
            message = f"Producto: {product}\nOferta actual: {offer}\nDescuento: {discount_percentage}\nPrecio anterior: {previous_price}\nEnlace: {link}"
            context.bot.send_message(chat_id, message)
    
    # Mostramos un mensaje al usuario indicando que la búsqueda ha finalizado
        context.bot.send_message(chat_id, "Búsqueda de ofertas completada.")
    else:
        context.bot.send_message(chat_id, "Lo siento, no se pudieron obtener las ofertas en este momento.")







def main():
    updater = Updater(token, use_context=True)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler('buscar_ofertas', buscar_ofertas))

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
    main()
 