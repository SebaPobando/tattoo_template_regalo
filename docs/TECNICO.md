# Documentación técnica

Para quien programa o mantiene el sitio. Si solo quieres instalarlo y
subirlo a internet, el paso a paso está en el [README](../README.md).

Hecho con **Flask + MySQL + HTML, CSS y JavaScript sin frameworks**. No hay
build ni npm: se configura un archivo y anda. Nace de una plantilla para
cafeterías; por eso algunos nombres internos siguen siendo de café (la tabla
del catálogo se llama `productos` y su ruta `/admin/carta`, los packs son
`combos`, el rol vendedor es `barista`, los pedidos para retiro viven en
`barra_*`). En pantalla todo dice lo de una tienda de tatuaje.

## Cómo se arma la base

No hay que correr SQL a mano. `instalar_base.py` crea la base (si puede) y
corre los archivos de `schema/` en orden; todos son idempotentes
(`CREATE TABLE IF NOT EXISTS`, `INSERT IGNORE`, `ALTER` condicionales), así
que se puede correr las veces que sea sin perder datos. Además **la app lo
corre sola al arrancar** (`server.py`), así que en Railway basta con
desplegar. Se apaga con `INSTALAR_AL_ARRANCAR=no`.

La conexión sale de `MYSQL_URL` (una sola variable, la de Railway) o de
`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` — ver
`flask_app/config/mysqlconnection.py`.

El primer administrador: `python crear_admin.py` en tu computador, o
`ADMIN_CORREO` + `ADMIN_CLAVE` en las variables (lo crea al arrancar si ese
correo no existe; después conviene borrarlas).

## Lo que cambió respecto de la plantilla de cafetería

- **Lo agotado se ve en el catálogo**, marcado «Agotado» (`Carta.menu()`
  devuelve `agotado: true`). En la cafetería se escondía.
- **Sin Shopify no hay tienda online**: la sección, el carrito, sus
  enlaces y las tarjetas del panel (destacados, pedidos de Shopify,
  ventas) solo aparecen con `SHOPIFY_DOMINIO`.
- **El vendedor atiende la cola de pedidos para retiro** (`/admin/barra`);
  abrir, cerrar y configurar sigue siendo del admin.
- La ficha técnica de Shopify usa metacampos `custom.marca`,
  `compatibilidad`, `contenido`, `medidas`, `registro`, `uso` y `garantia`.
- Paleta de papel y tinta (`static/css/tokens/colors.css`), títulos en
  Anton, mascotas apagadas por defecto.

## Seguridad antes de abrir al público

- [ ] `SECRET_KEY` propia y larga (la app no arranca en producción con una
      corta o la de ejemplo).
- [ ] `FLASK_ENV=production` y `DETRAS_DE_PROXY=1` en Railway.
- [ ] SMTP configurado y probado: en Railway el disco se borra en cada
      despliegue, así que sin SMTP los correos de verificación se pierden.
- [ ] Ninguna cuenta con rol distinto de cliente y sin contraseña:
      ```sql
      SELECT id, email, rol FROM usuarios
       WHERE password_hash IS NULL AND rol <> 'cliente';
      ```
- [ ] Los productos y el curso de ejemplo, borrados.
- [ ] `ADMIN_CLAVE` y `CARGAR_EJEMPLOS` borradas de las variables.
- [ ] `/health` responde `{"ok": true}`.

**Un solo worker de gunicorn, a propósito** (ver `Procfile`): los frenos
anti fuerza bruta viven en la memoria del proceso. Con más workers cada uno
lleva su propia cuenta.

## Estructura

```
flask_app/
├── config/
│   ├── negocio.py        ← LO QUE SE EDITA PARA CADA CLIENTE
│   ├── correo.py         envío de correos (con buzón de desarrollo)
│   ├── csrf.py           token anti-CSRF, sin dependencias
│   ├── enlaces.py        enlaces firmados de verificar y recuperar
│   ├── mysqlconnection.py conexión y transacciones
│   ├── qr.py             el QR del voucher
│   ├── rut.py            validación de RUT chileno
│   ├── seguridad.py      hashing de contraseñas (bcrypt)
│   ├── shopify.py        catálogo desde la Storefront API
│   └── tiempo.py         fechas en horario local
├── controllers/          rutas
├── models/               SQL, sin ORM
├── static/
│   ├── css/tokens/       colores, tipografía y espaciado
│   ├── img/              ← las imágenes de marcador se reemplazan acá
│   │   └── pwa/          los cuatro iconos de la app instalable
│   └── js/               carrito, agenda, muro, promo, cuenta
└── templates/            Jinja
    ├── _pwa.html         el <head> que hace instalable el sitio
    └── manifest.webmanifest   se sirve por ruta, con los datos del negocio
pruebas/                  suite de regresión (ver pruebas/README.md)
schema/                   la base de datos y sus migraciones
```

## Pruebas

```bash
python pruebas/suite.py
```

Levanta la app contra tu base local y revisa más de 120 comportamientos que
importan (unos más si tu `.env` de prueba tiene `SHOPIFY_WEBHOOK_SECRET`): que un bloqueado
pierda la sesión, que nadie se quede con una cuenta ajena, que el panel no se
abra sin rol, que las páginas públicas respondan, que la promo de la portada
aparezca y se baje cuando toca, que el manifest salga con el nombre del
cliente y sus iconos existan de verdad, que un pedido para retiro cobre el
precio de la base y no el del formulario y no entre en una franja llena, que la
ruleta no se gire dos veces ni sin que la habilite el admin, que un vale solo lo
canjee el personal y una sola vez, que el vendedor no entre a lo que no le toca, y que el webhook de pedidos de
Shopify rechace firmas falsas, guarde el nombre del comprador y no duplique
un pedido repetido ni invente uno al recibir un reembolso.

Correrlas después de cada personalización toma veinte segundos y evita
entregar un sitio roto. **Las dos últimas son las que más rinden al vender:**
un manifest que dice «Insumos Tattoo Ejemplo» o un icono que da 404 no se notan en el
navegador — se notan cuando el cliente instala su propio sitio en el teléfono
y ve el nombre de la plantilla.

El detalle de qué revisa cada bloque, y por qué tres de ellos existen, está en
[pruebas/README.md](../pruebas/README.md).

---

## Instalable en el teléfono (PWA)

La gente puede agregar el sitio a su pantalla de inicio y abrirlo sin barra
del navegador, como una app. No hay nada que activar: viene andando.

**El manifest se arma solo desde `negocio.py`.** Es una ruta de Flask
(`/manifest.webmanifest`), no un archivo estático, justamente para que una
instalación nueva no dependa de acordarse de editar un JSON aparte — que es
el archivo que se olvida y deja al teléfono del cliente diciendo
«Insumos Tattoo Ejemplo». El nombre, la descripción y los colores salen de ahí.

**Lo único que hay que reemplazar son los cuatro iconos** de
`static/img/pwa/`, que vienen como marcadores igual que el resto de las
imágenes. El script de más abajo los saca del logo del cliente.

**No hay service worker, y es a propósito.** Chrome dejó de exigirlo para
instalar (versión 108 en móvil, 112 en escritorio) justamente porque la gente
ponía uno vacío solo para cumplir el requisito. Lo único que lo sigue pidiendo
es el aviso automático de instalación; desde el menú del navegador se instala
igual. Si algún día se agrega uno, la regla es una: **red primero, y que nunca
cachee precios ni saldo.** Un service worker sirviendo el catálogo desde el caché
es exactamente la falla que el resto del proyecto evita, y la causa clásica
del «sigo viendo la versión vieja» después de cada despliegue.

### Detalles que cuestan encontrar después

**iOS ignora el manifest para el icono** y usa `apple-touch-icon`. Por eso esa
etiqueta va aparte, en `_pwa.html`.

**El icono `maskable` va al 58% del lienzo.** Android lo recorta en círculo,
squircle o gota según el lanzador del teléfono, y la zona segura es solo el
80% central. Un logo que llene el cuadrado entero se entrega con los bordes
comidos.

**La segunda marca no lleva manifest a propósito.** Es otra identidad, y
ofrecer «instalar la tienda» desde la página del estudio sería raro.
Solo lleva su `theme-color`, porque sin él la barra del navegador se queda con
el fondo de la tienda en una página oscura.

**`start_url` apunta a `/?origen=app`.** Ese parámetro no lo lee nadie: está
para poder distinguir en los registros del servidor cuánta gente entra desde
el icono instalado. El campo `id` queda fijo en `/` para que cambiar el
`start_url` más adelante no cree una app distinta en el teléfono de quien ya
la instaló.

### Generar los iconos del cliente

Con Pillow instalado (`pip install pillow`), desde la carpeta del proyecto y
con el logo del cliente ya puesto en `static/img/`:

```python
from PIL import Image

LOGO = 'flask_app/static/img/logo.png'     # el del cliente, cuadrado y con buen margen
FONDO = (247, 240, 228)                    # el color de fondo de la marca

logo = Image.open(LOGO).convert('RGBA')

def lienzo(lado, escala):
    salida = Image.new('RGB', (lado, lado), FONDO)
    objetivo = int(lado * escala)
    prop = logo.width / logo.height
    nw, nh = (objetivo, int(objetivo / prop)) if prop >= 1 else (int(objetivo * prop), objetivo)
    escalado = logo.resize((nw, nh), Image.LANCZOS)
    salida.paste(escalado, ((lado - nw) // 2, (lado - nh) // 2), escalado)
    return salida

D = 'flask_app/static/img/pwa'
lienzo(512, .78).save(f'{D}/icono-512.png', optimize=True)
lienzo(192, .78).save(f'{D}/icono-192.png', optimize=True)
lienzo(180, .78).save(f'{D}/apple-touch-icon.png', optimize=True)
lienzo(512, .58).save(f'{D}/icono-maskable-512.png', optimize=True)   # 58%: zona segura
```

---

## Categorías y packs del catálogo

### Categorías

Se crean, renombran y reordenan desde el bloque **«+ Agregar una categoría»**,
arriba del de productos en `/admin/carta/<marca>`. Va primero porque es el orden real de
trabajo: sin una categoría donde ponerlo, el formulario de producto no sirve.

- **El slug se calcula del nombre al crearla y no cambia al renombrarla.**
  Corregir una tilde no puede romper un enlace guardado a esa sección.
- Sin orden, la categoría nueva va **al final**: no descoloca un catálogo que ya
  estaba ordenado.
- Al lado de cada una se ve cuántos productos tiene.
- **No se borran desde el panel, a propósito.** Una categoría con productos la
  protege la llave foránea, y las salidas —bloquear o dejar esos productos sin
  categoría— se deciden mirando el caso, no con un botón que parece inofensivo.

### Packs (en el código, «combos»)

`/admin/carta/<marca>/combos`, o el enlace **Packs del catálogo** en la misma página.
Un pack es *«Pack bioseguridad semanal por $24.000»*: nombre y precio propios, y
varios productos adentro. En el código y en la base se llaman combos.

**No es una categoría llamada «Packs», y no puede serlo.** Un producto
pertenece a una sola categoría (`productos.categoria_id`), así que meter los
guantes en «Packs» los sacaría de «Bioseguridad». Y una categoría no tiene dónde
guardar el precio del combo. Por eso los combos tienen tabla propia
(`carta_combos` + `carta_combo_items`) y **referencian** productos que siguen
en sus categorías de siempre: si mañana se renombra un producto, el pack lo
muestra con el nombre nuevo. En la base no se llama `promos` porque esa tabla
ya existe y es el banner de la portada.

- **En el catálogo público salen primero**, como una sección «Packs», con
  *«Incluye: 1× Guantes, 1× Film barrera»* armado con los nombres reales. Tienen la
  misma forma que un producto, así que la portada y `/api/v1/menu` no tuvieron
  que cambiar.
- **Vigencia con dos fechas**, igual que el banner: empieza y termina, y
  editar el texto no reinicia ningún plazo. O **«sin fecha de término»**: corre
  hasta que lo apaguen. Eso se guarda como `fin_at` NULL y no como una fecha
  lejana — 2099 mentiría en pantalla y el contador del banner haría una
  cuenta regresiva de setenta años.
- **Un interruptor** lo baja al tiro sin tocar las fechas; al volver a
  encenderlo recupera su plazo original.
- **No se apaga solo cuando se agota un producto.** Decisión del dueño: el
  panel lo avisa (*«⚠ Film barrera está agotado — el pack sigue visible»*) y
  decide la persona. Que una promo desaparezca sin que nadie la tocara confunde
  más de lo que ayuda.
- **«Qué trae» tiene buscador**, y lo ya elegido nunca se oculta al buscar
  otra cosa — así no se manda un combo a medias sin notarlo.
- **No se pueden colar productos de otra marca** mandando un id a mano por
  POST: se descartan, y un combo sin productos válidos no se guarda.

**Orden y prioridad no son lo mismo.** *Orden* es la posición del combo dentro
de la sección «Packs». *Prioridad* solo importa si está marcado **«Mostrar en
el banner de la portada»**.

**El banner lee el combo; no lo copia.** Marcado, `Promo.vigente()` lo trae
desde `carta_combos` en la misma consulta que los banners normales — copiar
nombre y fechas a `promos` sería garantizar que algún día discrepen. Si hay
varios vigentes gana la prioridad más alta; a igualdad, el que termina antes,
y los sin término van al final. La clave que guarda el navegador al cerrar el
banner lleva el origen (`promo-3` / `combo-3`): sin eso, cerrar el banner 3
silenciaría también el combo 3. Un combo sin fecha sale en el banner **sin
contador**.

Necesita la migración `schema/carta_combos.sql`. En una base donde las tablas
ya existían, el `ALTER` del final vuelve `fin_at` opcional; se puede correr
las veces que sea.

## Pedidos para retiro

Un tatuador arma su pedido desde la página, elige cuándo pasa y lo retira
listo en el mesón. **Paga al retirar.** No es despacho ni Shopify: es
el catálogo de la tienda con un reloj.

**Se instala con** `schema/barra_pedidos.sql` y **nace apagado**: mientras
nadie lo abra desde `/admin/barra`, ningún enlace público lo menciona y
`/pedir` dice que no se están tomando pedidos. Al abrirlo aparecen un botón
«Pedir para retirar» bajo el catálogo y un enlace en el pie de página. (No en el
menú de arriba: ya no cabe nada más ahí.)

### Lo que decide el dueño, desde el panel

| | |
|---|---|
| **Días y horario** | Qué días se atiende y la ventana, en hora de Chile (11:00–19:00). Sigue siendo la misma hora cuando cambia el horario de verano. |
| **Franjas y cupos** | Cada cuántos minutos hay una franja y **cuántos pedidos alcanza a juntar el mesón en cada una**. |
| **Anticipación** | Con 20 minutos, a las 11:50 la primera hora que se ofrece es 12:15. |
| **Qué se puede pedir** | Qué categorías del catálogo y si entran los packs. Solo lo disponible. |
| **Dónde se retira** | En dos niveles: el barrio, que ve cualquiera, y la **dirección exacta, que solo ve quien ya pidió** (en la página de su pedido, con un botón al mapa). Útil si la tienda atiende con cita o desde un taller. |

### Lo que ve el cliente

- `/pedir`: el catálogo con contadores, las franjas como botones (las llenas,
  tachadas) y el total abajo. Sin cuenta: nombre y celular.
- `/pedido/<código>`: en qué va (Recibido → Juntando → Listo → Entregado),
  **se actualiza sola** cada 15 segundos con la pestaña abierta, y vibra
  cuando queda listo. Ahí está el botón **«Estoy afuera»**, y el de cancelar
  mientras nadie lo ha empezado a juntar.

### Lo que ve el dueño

`/admin/barra` es la cola del día por franja, con **un botón grande por
pedido con el siguiente paso** (Empezar a juntar → Marcar listo → Entregar
y cobrar). Entregar un pedido que se paga al retirar lo deja cobrado en el
mismo clic. Quien avisó que está afuera se ve resaltado. Si un número ya dejó
pedidos sin retirar antes, el pedido lo dice. La página se recarga sola
cuando entra algo nuevo, y el título de la pestaña cuenta los pedidos sin
tomar.

### Cómo se protege

- **El precio lo pone el servidor.** El formulario manda «2 del producto 14»;
  el precio sale de la base y se copia al pedido (si mañana la tinta sube, el
  pedido de ayer sigue diciendo lo que costó).
- **El último cupo no se vende dos veces.** Tomar una franja va en una
  transacción con `FOR UPDATE`: probado con ocho pedidos simultáneos por un
  cupo, entra uno.
- Máximo de unidades por pedido, máximo **2 pedidos en curso por celular**,
  y 6 pedidos por hora desde la misma conexión.

### Lo que viene

El pago en línea con Mercado Pago entra por este mismo módulo: la columna
`metodo_pago` ya lo contempla. Hasta que exista, **no se ofrece ningún botón
de pagar en línea**. Los textos de cada estado viven en `TEXTO_ESTADO`, en
`flask_app/models/barra_model.py`: si la tienda quiere otras palabras, se cambian ahí.

## Ruleta de premios

Quien compra sobre cierto monto **en la tienda** gira y se lleva lo que
salga. Se instala con `schema/ruleta.sql`.

### Cómo se usa en la caja

1. El cliente paga sobre el monto (por defecto $40.000; se cambia en el
   panel).
2. En **Panel → Ruleta → Habilitar giro**. La referencia es opcional
   (número de boleta, monto, nombre).
3. Aparece un **QR**: el cliente lo escanea y gira desde su celular. O se
   toca «Girar en este dispositivo» y gira en la tablet de la caja.
4. La ruleta da vueltas, frena y muestra el premio con su código. En el
   historial del panel queda quién ganó qué, y se marca «Entregado».

No hay `/ruleta` pública ni botón en la portada: **cada giro lo habilita
alguien del local**, porque la app no ve la boleta. Un giro sirve una sola vez
y vence a los 30 minutos si no se usa (configurable); también se puede
anular.

### Los premios

Se escriben en el panel, uno por gajo, entre 4 y 24 gajos. **Todos los gajos
tienen la misma probabilidad**: con 12, cada uno sale 1 de cada 12 veces.
Para que un premio salga más seguido se pone en más gajos, y el panel muestra
el % real de cada premio. La ruleta nace sin premios a propósito: una de
ejemplo regalando «Máquina gratis» porque nadie la cambió es un problema real.

### Por qué no se puede hacer trampa

- **El premio lo sortea el servidor** (`secrets.randbelow`), no la animación:
  el navegador recibe el resultado y anima la rueda hasta ese gajo. Probado
  con 1.932 giros: chi² = 9,9, muy por debajo del 19,7 que indicaría un
  gajo favorecido.
- **Girar dos veces devuelve lo mismo**: recargar o tocar dos veces no
  vuelve a sortear (transacción con `FOR UPDATE` sobre el giro).
- Cada giro guarda una **foto de la ruleta** como estaba al girar: si
  después se cambian los premios, el historial sigue diciendo la verdad.

Los colores de los gajos y las dos mascotas de arriba se configuran en
`negocio.py` (ver PERSONALIZAR.md). El sello del pie es el logo.

## Destacados de la tienda

Para lanzamientos y ediciones limitadas (solo con Shopify). En **Panel → Tienda:
destacados** aparecen los productos que hoy trae Shopify; en cada uno se
marca «Destacar» y se elige:

- **Color** del borde y de la cinta (once opciones). Es una lista cerrada a propósito, para que cualquier combinación se
  vea bien con la marca.
- **Cinta**: el texto sobre la foto, por ejemplo «Nuevo» o «Edición
  limitada».
- **Orden** entre los destacados (el menor va primero).

La miniatura de cada fila muestra cómo queda la tarjeta mientras se elige.

En la tienda, un destacado sale con su borde y su cinta, va **primero en la tienda y en su
categoría** y aparece en la
pastilla **«Especiales»**, segunda después de «Todos», que solo existe
mientras haya algún destacado. El orden de las categorías no cambia: lo
sigue mandando la colección de Shopify.

Los precios, fotos y stock siguen saliendo de Shopify; esta tabla
(`schema/tienda_destacados.sql`) guarda solo la decisión de cómo mostrar
cada producto, por su handle. Si un destacado deja de venir en el catálogo
(lo sacaron de la colección o le cambiaron la URL), el panel lo muestra en
«Ya no están en la tienda» para quitarlo.

## Vales de regalo y gift cards

Un vale es una tarjeta con QR que se canjea **una vez, completa**, en el
mesón. Se instala con `schema/vales.sql`.

| | **Vale de regalo** | **Gift card** |
|---|---|---|
| Quién lo origina | El local: un evento, una cortesía | Un cliente que la compra en caja |
| Se cobra | No | Sí: se anota cuánto pagó |
| Vence | Si quien lo emite elige una fecha | **Nunca**: está pagada |

Lo que cubre lo escribe quien lo emite, en texto libre: «1 caja de
cartuchos», «1 tinta de 120 ml», «$20.000 en compras». Sin saldo parcial: se
canjea entero.

**Emitir.** En **Panel → Vales** se elige el tipo, se escribe qué incluye y,
si se quiere, para quién y su celular. Al emitir se abre la página del vale
con **«Enviar por WhatsApp»**: el mensaje lleva el enlace a esa página, que
muestra el QR. **Para un evento**, «Emitir varios» crea hasta 200 vales
iguales y abre una hoja lista para imprimir y recortar (tres por fila en A4).

**Canjear.** El cliente muestra el QR; alguien del local lo escanea con la
cámara de su celular y se abre la misma página. **Solo si tiene sesión de
personal** (admin o vendedor) aparece el botón **«Canjear vale»**. Escanear
no canjea: hay que tocar el botón, para que revisar un vale no lo gaste. Un
cliente que abre su enlace ve su vale y nada más. El canje va en una
transacción con `FOR UPDATE`: probado con ocho canjes simultáneos del mismo
vale, pasa uno.

**Todos los vales**, de los dos tipos, quedan en la lista del panel con su
estado (vigente, canjeado, vencido, anulado), quién lo emitió y quién lo
canjeó, con filtros por tipo y estado. El admin ve además lo vendido en gift
cards y lo que queda sin canjear, y puede anular un vale o revertir un canje
hecho por error.

## El rol vendedor (barista en el código)

En la base el rol se llama `barista` (la plantilla viene de una cafetería);
en pantalla dice «vendedor(a)». Hay dos formas de tener uno, las dos en **Panel → Cuentas**:

- **Crear la cuenta** («Crear cuenta de vendedor(a)»): nombre, correo y, si se
  quiere, celular. La cuenta nace **sin contraseña** y el panel muestra un
  enlace para mandárselo por WhatsApp (también le llega por correo). Con él
  la persona elige su contraseña y entra directo al mesón. El enlace dura
  72 horas y sirve una vez; si vence, «Nuevo enlace» en su fila. El admin
  nunca conoce la contraseña de nadie.
- **Ascender una cuenta que ya existe:** si la persona ya se registró en el
  sitio, «Hacer vendedor(a)» en su fila.

Con su cuenta, el vendedor ve un panel reducido —**Vales**, **Ruleta** y, si están abiertos, **Pedidos para retiro**— y nada más:
ni precios, ni ventas, ni cuentas (el resto le responde 404). Atiende la cola de pedidos (sin tocar su configuración); en la ruleta
habilita giros y marca premios entregados; los premios los sigue editando
el admin. Quitarle el rol surte efecto al tiro, sin esperar a que cierre
sesión. Desde el panel no se puede crear ni quitar un admin.

## Pedidos de Shopify (webhook)

Cuando alguien paga en Shopify, Shopify le avisa al sitio y queda un registro
en `/admin/pedidos`. **Es un registro, no una billetera**: no suma ni
descuenta puntos — eso necesita el ledger que todavía no existe (ver
*Lo que no trae*). Por ahora sirve para que el dueño vea, sin entrar a
Shopify, qué se vendió y a quién, sin tener que abrir el panel de Shopify.

**No se activa solo**, a diferencia del resto de la plantilla. Requiere un
paso manual en Shopify, y ese paso necesita que el sitio ya esté desplegado
con una URL pública: crear un webhook de tipo «Order payment»
(Configuración → Notificaciones → Webhooks, en el admin de Shopify) apuntando
a `https://<dominio>/webhooks/shopify/orders-paid`, y copiar el secreto que
Shopify entrega a `SHOPIFY_WEBHOOK_SECRET` en `.env`. Sin ese secreto
configurado el webhook rechaza cualquier aviso (401) en vez de guardar algo
que no puede confirmar que vino de Shopify.

**La firma se verifica siempre**, comparando el encabezado
`X-Shopify-Hmac-Sha256` del aviso contra un HMAC calculado con el secreto —
así nadie puede inventar pedidos falsos apuntando al endpoint. Los avisos
repetidos (Shopify reintenta si el sitio no responde a tiempo) no duplican el
pedido: se identifica por su `id` de Shopify.

**El panel muestra más que el monto**: el nombre de quien compró (aunque
compre sin cuenta), el detalle de cada ítem con cantidad y precio, un link
directo a la orden en el admin de Shopify, y los pedidos agrupados por día
(«Hoy», «Ayer», y la fecha para los más viejos).

**Las ventas se miran por día, semana, mes o año.** Un selector arriba del
listado reagrupa los pedidos según el corte elegido, y cada encabezado trae
cuántos pedidos y cuánto se vendió en ese período. El corte viaja en la URL
(`?periodo=mes`), así que se puede dejar marcado o compartir.

Dos detalles de cómo se cuenta la plata, porque equivocarse ahí en silencio
sería el peor modo de fallar de este panel. Uno: **los totales se calculan
sobre todos los pedidos**, no sobre los que alcanzan a listarse — si un
período tiene más pedidos de los que se muestran, el encabezado avisa
cuántos quedaron fuera del listado, pero su total ya los incluye. Dos: **lo
reembolsado no suma**, ni en los totales por período ni en la pastilla de
arriba; se sigue contando como pedido y se avisa al lado cuántos quedaron
fuera de la suma. Un reembolso *parcial* sí suma completo, porque Shopify
avisa que hubo devolución pero este registro no guarda de cuánto fue.

**El dashboard vive aparte, en `/admin/ventas`.** `/admin/pedidos` es la
bitácora —qué se vendió y a quién—; `/admin/ventas` responde la otra
pregunta, cómo va el negocio: la evolución en el tiempo, los productos más
vendidos, el ticket promedio y la comparación con el período anterior. Usa
el mismo `?periodo=` que el panel, así que se salta de una página a la otra
sin perder el corte.

Los gráficos son **SVG armado en el servidor**: sin librería de gráficos y
sin JavaScript. La geometría se calcula en el controlador y la plantilla
solo pinta lo que recibe, así que la página funciona con el JS apagado y la
plantilla no suma una dependencia. Cada gráfico trae además su tabla de
números (`<details>`), porque un valor nunca debería estar disponible solo
al pasar el mouse por encima.

Dos cosas que el gráfico dice a propósito: la barra del período en curso va
en un verde más claro, porque comparar un mes a medio andar contra meses
cerrados es la trampa clásica de estos paneles; y los períodos sin ventas
se dibujan en cero en vez de saltarse, para que un mal mes se vea como un
mal mes y no como un mes que no existió.

**Un segundo webhook avisa los reembolsos.** Si alguien devuelve un pedido
después de pagarlo, un reembolso hecho solo en Shopify dejaría el registro
mintiendo — se seguiría viendo como venta normal. Por eso hay OTRO webhook,
de tipo «Order updated» (`/webhooks/shopify/orders-updated`, mismo
`SHOPIFY_WEBHOOK_SECRET` de arriba), que revisa el `financial_status` de
cada aviso y marca el pedido como reembolsado o con reembolso parcial —
nunca crea un pedido nuevo, solo actualiza uno que ya existía. Es opcional:
sin ese segundo webhook, el registro sigue funcionando, solo que no se
entera de un reembolso posterior.

### Crear los webhooks en Shopify

Necesita el sitio ya desplegado, con URL pública.

1. En el admin de Shopify: **Configuración → Notificaciones → Webhooks →
   Crear webhook**.
2. Evento: **«Order payment» / «Pago de pedido»**. Formato: JSON.
3. URL: `https://<dominio>/webhooks/shopify/orders-paid`.
4. Esa misma página muestra el secreto de firma (uno para todos los
   webhooks de ahí). Copiarlo en `SHOPIFY_WEBHOOK_SECRET`, en las variables
   del servicio. No es el mismo que `SHOPIFY_STOREFRONT_TOKEN`.
5. Hacer un pedido de prueba y confirmar que aparece en `/admin/pedidos`.

Opcional, para los reembolsos: un segundo webhook con evento **«Order
updated»** apuntando a `https://<dominio>/webhooks/shopify/orders-updated`,
con el mismo secreto.
