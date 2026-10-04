# Ponerle la marca de la tienda

La plantilla viene con nombre, textos y fotos **de ejemplo**. Esta guía
explica cómo cambiarlos por los de la tienda de verdad. No hace falta saber
programar: se editan archivos de texto y se reemplazan imágenes.

> Para abrir y editar los archivos sirve el **Bloc de notas** (Windows) o
> **TextEdit** (Mac, en modo «texto sin formato»). Más cómodo es
> [Visual Studio Code](https://code.visualstudio.com/), que es gratis y
> colorea el texto para que sea más fácil no equivocarse.

---

## 1. Qué pedirle a la dueña o al dueño de la tienda

- Nombre exacto de la tienda, como quiere que se lea.
- Una frase corta que diga qué es (va bajo el nombre).
- Dirección, ciudad, región y horario de atención.
- Correo, número de WhatsApp (con el 56 adelante) e Instagram.
- Cómo se van a llamar los puntos y cuántos pesos vale cada uno.
- Si tiene ficha en Google Maps: el enlace (de ahí sale el botón para dejar
  reseñas), la nota y cuántas reseñas tiene.
- **Imágenes**: el logo (cuadrado), una foto principal horizontal (el local,
  el mesón o productos), una foto del equipo y una imagen para compartir.
- Si ya vende con **Shopify**, avísame: se conecta aparte (ver el punto 7).

## 2. El archivo que manda: `negocio.py`

Está en `flask_app/config/negocio.py`. Ábrelo y busca estas líneas. **Cambia
solo lo que está entre comillas** en el segundo valor; no borres las
comillas ni los paréntesis.

```python
NOMBRE = _env("MARCA_NOMBRE", "Insumos Tattoo Ejemplo")     # ← el nombre completo
NOMBRE_CORTO = _env("MARCA_NOMBRE_CORTO", "Insumos")        # ← lo grande del logo
TAG = _env("MARCA_TAG", "TATTOO")                           # ← la palabra chica al lado
LEMA = _env("MARCA_LEMA", "Insumos de tatuaje para profesionales")
HERO_TITULO = _env("MARCA_HERO_TITULO", "Todo para tu estación, en un solo lugar")

CIUDAD = _env("MARCA_CIUDAD", "Tu Ciudad")
REGION = _env("MARCA_REGION", "Tu Región")
DIRECCION = _env("MARCA_DIRECCION", "Calle Principal 123")
HORARIO = _env("MARCA_HORARIO", "Lun–Vie · 11:00–20:00 || Sáb · 11:00–15:00")   # || separa líneas

CORREO = _env("MARCA_CORREO", "hola@insumostattoo.cl")
TELEFONO = _env("MARCA_TELEFONO", "+56 9 0000 0000")
WHATSAPP = _env("MARCA_WHATSAPP", "56900000000")            # ← solo números, con el 56
INSTAGRAM = _env("MARCA_INSTAGRAM", "")                     # ← solo el usuario, sin @

PUNTOS_NOMBRE = _env("MARCA_PUNTOS_NOMBRE", "Puntos Tinta")
PUNTOS_SIGLA = _env("MARCA_PUNTOS_SIGLA", "PT")
PUNTOS_POR_PESO = int(_env("MARCA_PUNTOS_POR_PESO", "10"))  # ← 1 punto = $10
```

Por ejemplo, para una tienda que se llama «Ink Supply Sur»:

```python
NOMBRE = _env("MARCA_NOMBRE", "Ink Supply Sur")
```

**Los colores** están más abajo en el mismo archivo. Son códigos como
`#161616`; puedes elegirlos en
[htmlcolorcodes.com](https://htmlcolorcodes.com/es/) y copiar el código:

```python
COLOR_ACENTO = ...      # botones y enlaces (por defecto, negro tinta)
COLOR_TEXTO = ...       # el texto
COLOR_FONDO = ...       # el fondo de la página
COLOR_DESTACADO = ...   # los puntos y lo destacado (por defecto, rojo)
```

**Las reseñas de Google** (opcional): pon el Place ID de la ficha de la tienda,
la nota y la cantidad de reseñas. El Place ID se busca escribiendo el nombre
de la tienda en
[esta página de Google](https://developers.google.com/maps/documentation/places/web-service/place-id).
Si lo dejas vacío, el botón de reseñas simplemente no aparece.

Después de guardar, **detén la app (Ctrl + C) y vuelve a correr
`python server.py`** para ver los cambios.

## 3. Las imágenes

Están en `flask_app/static/img/`. Cada una dice qué va ahí. Reemplázalas
**con el mismo nombre de archivo** y listo:

| Archivo | Qué va | Medida |
|---|---|---|
| `logo.png` | El logo, cuadrado | 400 × 400 o más |
| `hero.jpg` | La foto principal (arriba de todo) | 1600 × 1000 |
| `equipo.jpg` | La foto de «Quiénes somos» | 1200 × 900 |
| `og-cover.jpg` | La que aparece al compartir el enlace por WhatsApp | 1200 × 630 |
| `pwa/icono-192.png`, `pwa/icono-512.png`, `pwa/apple-touch-icon.png`, `pwa/icono-maskable-512.png` | El ícono cuando alguien instala el sitio en el teléfono | ver [docs/TECNICO.md](docs/TECNICO.md) |

Ojo con la extensión: si el archivo nuevo es `.png` y el antiguo era `.jpg`,
o lo conviertes o cambias el nombre en `negocio.py` (`IMAGEN_HERO = ...`).

## 4. Los textos de la portada

`negocio.py` cubre nombre, contacto y colores. Los textos largos de la portada
—el párrafo de «Quiénes somos», sus cifras (año de fundación, productos,
estudios clientes) y los pasos del programa de puntos— están en
`flask_app/templates/landing.html`. Busca (Ctrl + F) estas frases y
reemplázalas:

- «Hecho por tatuadores, para tatuadores»
- «Sabemos lo que es quedarse sin cartuchos»
- «Trabajamos con marcas que probamos»
- «Año de fundación», «Productos», «Estudios clientes»

Es el paso que más se olvida y el que más se nota.

## 5. El catálogo

Se carga desde el panel: entra con tu cuenta de administración y ve a
**Panel → Catálogo**. Ahí:

- **Categorías**: vienen Cartuchos, Agujas y tubos, Tintas, Máquinas, Fuentes
  de poder, Bioseguridad, Cuidado post-tatuaje y Accesorios. Se renombran,
  se reordenan y se agregan nuevas.
- **Productos**: nombre, descripción, precio, una etiqueta opcional («Nuevo»,
  «Más vendido») y un interruptor para marcar **agotado**. Lo agotado sigue a
  la vista, en gris, para que el tatuador sepa que vuelve.
- **Packs**: varios productos a un precio («Kit de inicio»).

**Antes de abrir al público, borra los productos de ejemplo** (o cámbiales
nombre y precio) y el curso de ejemplo de **Panel → Cursos**.

## 6. Lo que se enciende y se apaga

| Qué | Dónde | Por defecto |
|---|---|---|
| Pedidos para retirar en tienda | Panel → Pedidos para retiro → Configuración | Apagado |
| Ruleta de premios | Panel → Ruleta (escribe los premios) | Sin premios |
| Promo con cuenta regresiva | Panel → Promos | Ninguna |
| Ilustraciones (mascotas) | `MASCOTAS` en `negocio.py` | Apagadas |
| Página del estudio (si la tienda tiene uno) | `SEGUNDA_ACTIVA` en `negocio.py` (`MARCA2_ACTIVA`) | Apagada |
| Tienda online con Shopify | `.env` / Variables (punto 7) | Apagada |
| Temporadas (Halloween, Navidad…) | `flask_app/config/temporadas.py` | Ninguna |

## 7. Shopify (solo si la tienda ya lo usa)

Si la tienda vende online con Shopify, el sitio puede mostrar esos productos
con su precio y stock y armar el carrito. Se configura con `SHOPIFY_DOMINIO`,
`SHOPIFY_STOREFRONT_TOKEN` y `SHOPIFY_COLECCION` (los pasos para sacar el
token están en `.env.example`). En Shopify conviene completar el campo
**«Tipo de producto»** (Cartuchos, Tintas…): con eso se arman las pestañas.

Sin Shopify no pasa nada: la sección no aparece y el catálogo propio con los
pedidos para retirar hace ese trabajo.

## 8. Antes de entregarlo

- [ ] Buscar «Ejemplo» y «Tu Ciudad» en el sitio: no debe quedar ninguno.
- [ ] Abrir la portada en el teléfono, no solo en el computador.
- [ ] Pegar el enlace en un chat de WhatsApp y ver que salga la imagen.
- [ ] Registrarse con un correo de verdad y ver que llega el correo (si no
      llega, falta configurar el correo: ver el README).
- [ ] Cambiar un precio desde el panel y verlo cambiar en la portada.
- [ ] Hacer un pedido de prueba para retirar y verlo en el panel.

## 9. Qué le enseñas a la tienda (media hora)

1. Cambiar un precio y marcar un producto como agotado.
2. Abrir los pedidos para retiro y atender uno de prueba.
3. Crear un curso, publicarlo y confirmar una inscripción.
4. Emitir un vale y canjearlo escaneando el QR.
5. Habilitar un giro de la ruleta.
6. Aprobar un mensaje del muro.
7. Crear la cuenta de alguien del mesón (Panel → Cuentas → Crear cuenta de
   vendedor(a)).
