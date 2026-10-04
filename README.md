# Sitio web para una tienda de insumos de tatuaje

Un sitio completo para una tienda que vende insumos a tatuadores y estudios:

- **Catálogo** con precios y stock a la vista (lo agotado se ve marcado).
- **Pedidos para retirar en tienda**: el tatuador arma su pedido, elige
  cuándo pasa y paga al retirar.
- **Cursos y capacitaciones** con inscripción, cupos, voucher con QR y botón
  para agregarlo al calendario.
- **Programa de puntos**, **vales de regalo y gift cards** con QR,
  **ruleta de premios**, **promos con cuenta regresiva**, **muro de la
  comunidad** y botón para **dejar reseñas en Google**.
- **Panel de administración** para manejar todo sin tocar código, y cuentas
  para el personal del mesón.

Si quieres entender de dónde sale cada parte, lee [ANALISIS.md](ANALISIS.md).

Esta guía está escrita **para personas que no son del mundo de la
informática**. Va paso a paso: primero lo haces andar en tu computador, y
después lo subes a internet con Railway.

---

## Índice

- [Antes de empezar](#antes-de-empezar)
- [Parte 1 — Hacerlo andar en tu computador](#parte-1--hacerlo-andar-en-tu-computador)
- [Parte 2 — Ponerle la marca de la tienda](#parte-2--ponerle-la-marca-de-la-tienda)
- [Parte 3 — Subirlo a internet con Railway](#parte-3--subirlo-a-internet-con-railway)
- [Parte 4 — Primeros pasos en el panel](#parte-4--primeros-pasos-en-el-panel)
- [Si algo sale mal](#si-algo-sale-mal)
- [Qué hay en cada carpeta](#qué-hay-en-cada-carpeta)

---

## Antes de empezar

**Qué necesitas**

- Un computador con Windows 10/11 o Mac.
- Conexión a internet.
- Una o dos horas la primera vez (después es mucho más rápido).
- Para la Parte 3: una cuenta de correo para crear cuentas gratis en GitHub y
  Railway.

**Cuatro palabras que vas a leer harto**

| Palabra | Qué es |
|---|---|
| **Terminal** | Una ventana negra donde se escriben comandos. Da miedo al principio, pero solo vas a copiar y pegar. |
| **Carpeta del proyecto** | La carpeta `tatuaje_template`, donde está este archivo. |
| **Base de datos (MySQL)** | El programa que guarda los productos, las cuentas y los pedidos. |
| **Servidor** | El programa que muestra el sitio. En tu computador lo prendes tú; en internet lo mantiene Railway. |

> **Cómo leer los comandos.** Cuando veas un cuadro gris como este:
>
> ```
> python --version
> ```
>
> significa: cópialo, pégalo en la terminal y aprieta **Enter**. Para pegar
> en la terminal de Windows usa **clic derecho** o **Ctrl + V**; en Mac,
> **Cmd + V**.

---

## Parte 1 — Hacerlo andar en tu computador

### Paso 1. Instalar Python

Python es el lenguaje en que está hecho el sitio.

**En Windows**

1. Entra a [python.org/downloads](https://www.python.org/downloads/) y toca
   el botón amarillo **Download Python** (cualquier versión 3.12 o más nueva
   sirve).
2. Abre el archivo que se descargó.
3. **MUY IMPORTANTE:** en la primera pantalla, marca la casilla
   **«Add python.exe to PATH»** (abajo). Si no la marcas, nada de lo que
   sigue va a funcionar.
4. Toca **Install Now** y espera a que termine. Toca **Close**.

**En Mac**

1. Entra a [python.org/downloads](https://www.python.org/downloads/) y
   descarga el instalador para macOS.
2. Ábrelo y sigue los pasos (Continuar, Aceptar, Instalar). Te va a pedir la
   contraseña de tu Mac.

**Para comprobar que quedó bien**, abre una terminal:

- Windows: tecla de Windows → escribe **cmd** → abre **Símbolo del sistema**.
- Mac: Cmd + Espacio → escribe **Terminal** → Enter.

Y escribe (en Mac usa `python3` en vez de `python`):

```
python --version
```

Debería responder algo como `Python 3.13.1`. Si dice que «no se reconoce»,
mira [Si algo sale mal](#si-algo-sale-mal).

### Paso 2. Instalar MySQL (la base de datos)

**En Windows**

1. Entra a [dev.mysql.com/downloads/mysql](https://dev.mysql.com/downloads/mysql/).
2. Elige la versión **8.4 (LTS)**, sistema **Microsoft Windows**, y descarga
   el **MSI Installer**. Si te pide iniciar sesión, abajo dice
   **«No thanks, just start my download»**.
3. Abre el instalador: **Next**, acepta la licencia, elige **Typical** e
   **Install**. (Si te pide instalar «Visual C++ Redistributable», acéptalo.)
4. Al terminar se abre **MySQL Configurator**. Toca **Next** en todo, salvo en
   la pantalla de cuentas (**Accounts and Roles**): ahí escribe una
   **contraseña para el usuario root** dos veces.
5. **Anota esa contraseña.** La vas a necesitar en el Paso 6.
6. Sigue con **Next** hasta **Execute** y luego **Finish**. MySQL queda
   funcionando solo cada vez que prendes el computador.

**En Mac**

1. Entra a [dev.mysql.com/downloads/mysql](https://dev.mysql.com/downloads/mysql/),
   versión **8.4 (LTS)**, sistema **macOS**, y descarga el **DMG** (elige
   **ARM** si tu Mac tiene chip M1/M2/M3/M4, o **x86** si es Intel).
2. Abre el `.pkg` que viene adentro y sigue los pasos.
3. Cuando te lo pida, escribe una **contraseña para root** y **anótala**.
4. Deja marcada la opción de iniciar MySQL. Queda funcionando solo.

### Paso 3. Dejar la carpeta del proyecto en un lugar fácil

Copia la carpeta `tatuaje_template` a **Documentos**. Si te llegó en un
`.zip`, descomprímelo primero (clic derecho → **Extraer todo** en Windows;
doble clic en Mac).

### Paso 4. Abrir una terminal DENTRO de la carpeta

Todos los comandos que siguen se escriben con la terminal «parada» en la
carpeta del proyecto.

**En Windows:** abre la carpeta `tatuaje_template` en el Explorador de
archivos. Haz clic en la **barra de direcciones** (arriba, donde dice la ruta),
borra lo que dice, escribe `cmd` y aprieta **Enter**. Se abre una terminal
ya ubicada en la carpeta.

**En Mac:** abre Terminal, escribe `cd ` (con un espacio al final, sin
Enter todavía), **arrastra la carpeta** `tatuaje_template` desde el Finder a
la ventana de la terminal y recién ahí aprieta **Enter**.

Para comprobar que estás en el lugar correcto, escribe `dir` (Windows) o
`ls` (Mac): debería aparecer una lista con `README.md`, `server.py` y otros.

### Paso 5. Preparar el entorno e instalar lo necesario

Esto se hace **una sola vez**. Crea una carpeta `venv` con todo lo que el
sitio necesita, sin ensuciar el resto de tu computador.

**En Windows:**

```
python -m venv venv
```
```
venv\Scripts\activate
```
```
pip install -r requirements.txt
```

**En Mac:**

```
python3 -m venv venv
```
```
source venv/bin/activate
```
```
pip install -r requirements.txt
```

Después del segundo comando, al principio de la línea aparece **`(venv)`**:
eso significa que el entorno está activo. El tercero descarga cosas durante
uno o dos minutos; es normal que llene la pantalla de texto.

> Desde acá, en Mac también puedes escribir `python` (sin el 3) mientras
> veas `(venv)` al principio de la línea.

### Paso 6. Crear la configuración

```
python configurar.py
```

Te va a preguntar los datos de MySQL. Aprieta **Enter** para aceptar lo que
viene entre corchetes (servidor, puerto, usuario) y escribe **la contraseña de
root que anotaste en el Paso 2** (mientras la escribes no se ve nada en la
pantalla: es normal). Si todo está bien, dice **«¡Conectó!»** y crea un
archivo `.env`.

> El archivo `.env` guarda tu contraseña. **No lo compartas ni lo subas a
> internet.** (Ya está configurado para que GitHub no lo suba.)

### Paso 7. Crear la base de datos

```
python instalar_base.py --ejemplos
```

Crea todas las tablas y carga un **catálogo de ejemplo** (cartuchos, tintas,
guantes…) para que veas cómo queda. Al final dice **«[OK] Base de datos
lista»**. Se puede repetir sin miedo: nunca borra nada.

### Paso 8. Crear tu cuenta de administración

```
python crear_admin.py
```

Escribe tu correo y una contraseña de **10 caracteres o más** (tampoco se ve
mientras la escribes). Confirma con `s` cuando te pregunte.

### Paso 9. ¡Prender el sitio!

```
python server.py
```

Abre tu navegador y entra a **[http://localhost:5000](http://localhost:5000)**.
Ahí está el sitio. El panel de administración está en
**[http://localhost:5000/admin](http://localhost:5000/admin)** (entra con la
cuenta del Paso 8).

Para **apagarlo**, vuelve a la terminal y aprieta **Ctrl + C**.

> **Mac:** si dice que el puerto 5000 está ocupado, es AirPlay. Usa
> `PORT=5001 python server.py` y entra a http://localhost:5001.

### Cada vez que lo quieras volver a abrir

Los pasos 1 a 8 se hacen una sola vez. Las próximas veces:

1. Abre la terminal en la carpeta (Paso 4).
2. Activa el entorno: `venv\Scripts\activate` (Windows) o
   `source venv/bin/activate` (Mac).
3. `python server.py`

---

## Parte 2 — Ponerle la marca de la tienda

El nombre, el contacto, los colores y los puntos se cambian en **un solo
archivo**: `flask_app/config/negocio.py`. Las fotos se reemplazan en
`flask_app/static/img/` con el mismo nombre de archivo.

Todo eso, con ejemplos y una lista de qué pedirle a la tienda, está en
**[PERSONALIZAR.md](PERSONALIZAR.md)**.

Después de cambiar algo: **Ctrl + C** en la terminal y de nuevo
`python server.py`.

---

## Parte 3 — Subirlo a internet con Railway

Railway es un servicio que mantiene el sitio prendido en internet, con su
base de datos incluida. Es de los más simples. El camino es:

**tu carpeta → GitHub (guarda el código) → Railway (lo publica)**

> **Costos (octubre 2026).** Railway da una prueba con **5 dólares de
> crédito** de regalo. Después, el plan **Hobby cuesta 5 dólares al mes** e
> incluye 5 dólares de uso, que normalmente alcanzan para un sitio así con
> su base de datos. Revisa los precios vigentes en
> [railway.com/pricing](https://railway.com/pricing). GitHub es gratis.

### Paso 1. Crear una cuenta en GitHub

Entra a [github.com](https://github.com/) → **Sign up** y sigue los pasos.

### Paso 2. Subir la carpeta a GitHub con GitHub Desktop

GitHub Desktop es un programa con botones, para no usar comandos.

1. Descárgalo de [desktop.github.com](https://desktop.github.com/), instálalo
   e inicia sesión con tu cuenta de GitHub.
2. Menú **File → Add local repository…** y elige la carpeta
   `tatuaje_template`.
3. Te va a decir que no es un repositorio y ofrecerte **create a
   repository**: tócalo. Deja el nombre como está y toca
   **Create repository**.
4. Arriba aparece el botón **Publish repository**. Tócalo, **deja marcada la
   casilla «Keep this code private»** (así nadie más ve el código) y toca
   **Publish repository**.

Listo: el código está en GitHub. El archivo `.env` y la carpeta `venv` **no**
se suben (está configurado así a propósito).

### Paso 3. Crear la cuenta en Railway

Entra a [railway.com](https://railway.com/) → **Login** → **Login with
GitHub** y autoriza.

### Paso 4. Crear el proyecto desde GitHub

1. En Railway toca **New Project** (o **+ New**).
2. Elige **Deploy from GitHub repo** (o **GitHub Repository**).
3. Si te pide permiso para ver tus repositorios, dáselo (puedes darlo solo
   para `tatuaje_template`).
4. Elige **tatuaje_template**.

Railway empieza a construir el sitio. **Es normal que este primer intento
falle o quede a medias**: todavía le falta la base de datos y la
configuración, que es lo que sigue.

### Paso 5. Agregar la base de datos

1. Dentro del proyecto, toca **+ Create** (o **+ New**, arriba a la derecha).
2. Elige **Database → MySQL**.
3. Aparece una nueva tarjeta llamada **MySQL**. No le cambies el nombre.

### Paso 6. Generar la clave secreta

En **tu computador**, en la terminal (con `(venv)` activo), escribe:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Aparece una línea larga de letras y números. **Cópiala**: es tu
`SECRET_KEY`. (Una distinta para cada sitio; no la compartas.)

### Paso 7. Configurar las variables

1. En Railway, toca la tarjeta del sitio (la que se llama
   **tatuaje_template**, no la de MySQL).
2. Ve a la pestaña **Variables** y toca **Raw Editor**.
3. Pega esto, **cambiando** lo que está en mayúsculas:

```
SECRET_KEY=PEGA-ACÁ-LA-CLAVE-DEL-PASO-6
FLASK_ENV=production
DETRAS_DE_PROXY=1
MYSQL_URL=${{MySQL.MYSQL_URL}}
ADMIN_CORREO=TU-CORREO@EJEMPLO.CL
ADMIN_CLAVE=UNA-CONTRASEÑA-DE-10-O-MÁS
CARGAR_EJEMPLOS=si
```

   - `MYSQL_URL=${{MySQL.MYSQL_URL}}` va **tal cual**: así el sitio se
     conecta solo a la base del Paso 5.
   - `ADMIN_CORREO` y `ADMIN_CLAVE` crean tu cuenta de administración la
     primera vez que el sitio arranca.
   - `CARGAR_EJEMPLOS=si` carga el catálogo de ejemplo. Si prefieres
     partir vacío, no pongas esa línea.

4. Toca **Update Variables**. Railway muestra un aviso para aplicar los
   cambios: toca **Deploy** (o **Apply changes**).

El sitio se vuelve a construir. **La base de datos se arma sola** cuando el
sitio arranca: no hay que hacer nada más. Puedes mirar el avance en la
pestaña **Deployments** → **View logs**; cuando todo está bien, aparece una
línea que dice **«Base de datos al día»**.

### Paso 8. Darle una dirección web

1. En la tarjeta del sitio, ve a **Settings → Networking**.
2. Toca **Generate Domain**. Si pregunta el puerto, acepta el que sugiere.
3. Aparece una dirección como `tatuaje-template-production.up.railway.app`.
   **¡Ese es tu sitio en internet!**

Entra, ve a `/login` (por ejemplo
`https://tatuaje-template-production.up.railway.app/login`) con el correo y
la contraseña que pusiste en `ADMIN_CORREO` y `ADMIN_CLAVE`.

### Paso 9. Ordenar las variables

Una vez que entraste al panel, vuelve a **Variables** y **borra**
`ADMIN_CLAVE` y `CARGAR_EJEMPLOS` (ya no se necesitan, y es más seguro no
dejar una contraseña escrita ahí). Railway vuelve a desplegar solo.

### Cómo publicar cambios después

Cada vez que cambies algo en la carpeta (un texto, una foto, `negocio.py`):

1. Abre **GitHub Desktop**: a la izquierda verás los archivos cambiados.
2. Abajo a la izquierda escribe un resumen corto (ej.: «Cambio el logo») y
   toca **Commit to main**.
3. Arriba toca **Push origin**.

Railway se da cuenta solo y publica la versión nueva en uno o dos minutos.

> Los productos, precios, cursos y promos **no** necesitan esto: se cambian
> directamente desde el panel del sitio publicado.

### Opcional: un dominio propio (www.tutienda.cl)

En la tarjeta del sitio: **Settings → Networking → Custom Domain**, escribe el
dominio y Railway te dice qué registro agregar donde lo compraste (en Chile,
normalmente [NIC Chile](https://www.nic.cl/)). Después cambia `DOMINIO` en
`negocio.py` por la dirección nueva.

### Muy recomendado: que los correos se envíen de verdad

Sin esto, los correos (confirmar la cuenta, recuperar la contraseña, el
voucher de los cursos) **no salen**: en Railway se pierden. Con una cuenta de
Gmail:

1. En tu cuenta de Google, activa la **Verificación en dos pasos**.
2. Entra a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   crea una **contraseña de aplicación** (ponle de nombre «Sitio tienda») y
   copia las 16 letras, sin espacios.
3. Agrega estas variables en Railway (pestaña **Variables**):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=TU-CORREO@gmail.com
SMTP_PASSWORD=LAS-16-LETRAS
CORREO_DESDE=TU-CORREO@gmail.com
CORREO_NOMBRE=Nombre de la tienda
```

Pruébalo creando una cuenta nueva en el sitio con otro correo: debería
llegarte el mensaje para confirmarla.

---

## Parte 4 — Primeros pasos en el panel

Entra a `/admin` con tu cuenta. Lo primero:

1. **Catálogo**: borra los productos de ejemplo (o cámbiales nombre y
   precio) y carga los de la tienda. El interruptor de cada producto lo marca
   como **agotado**.
2. **Cursos**: borra el curso de ejemplo o edítalo. Los cursos nuevos nacen
   en borrador: no se ven hasta que los publicas.
3. **Pedidos para retiro**: si la tienda quiere recibir pedidos online, ábrelos
   en **Configuración** (días, horario y cuántos pedidos alcanzan a juntar
   por franja).
4. **Cuentas → Crear cuenta de vendedor(a)**: para quien atiende el mesón.
   Le llega un enlace para elegir su contraseña; entra a vales, ruleta y
   pedidos, y a nada más.
5. **Ruleta**: escribe los premios si la vas a usar.
6. **Promos**: un banner con cuenta regresiva para la portada.

---

## Si algo sale mal

| Lo que ves | Qué hacer |
|---|---|
| `'python' no se reconoce como un comando` (Windows) | Prueba con `py` en vez de `python`. Si tampoco, desinstala Python y vuelve a instalarlo **marcando «Add python.exe to PATH»**. Cierra y abre la terminal. |
| `command not found: python` (Mac) | Usa `python3`. |
| No aparece `(venv)` o dice que no puede activar | En Windows, asegúrate de estar en **Símbolo del sistema** (cmd), no en PowerShell. Y de estar dentro de la carpeta (Paso 4). |
| `Access denied for user 'root'` | La contraseña de MySQL no es la correcta. Corre de nuevo `python configurar.py`. |
| `Can't connect to MySQL server` | MySQL está apagado. Windows: tecla Windows → **Servicios** → busca **MySQL84** → clic derecho → **Iniciar**. Mac: Configuración del Sistema → **MySQL** → **Start**. |
| `No module named ...` | Falta activar el entorno (`(venv)`) o instalar: `pip install -r requirements.txt`. |
| En Mac, «Address already in use» al prender | Usa `PORT=5001 python server.py`. |
| El sitio en Railway muestra «Application failed to respond» | Mira **Deployments → View logs**. Lo más común: falta una variable del Paso 7, o la `SECRET_KEY` es muy corta. |
| En Railway no puedo entrar con mi correo | Revisa que `ADMIN_CORREO` y `ADMIN_CLAVE` estuvieran bien escritas antes del primer arranque. Si no, desde tu computador puedes cambiar el `.env` para apuntar a la base de Railway, pero es más fácil pedir ayuda a alguien que programe. |
| Cambié `negocio.py` y no se ve | Apaga (Ctrl + C) y prende de nuevo (`python server.py`). En Railway: commit + push (ver «Cómo publicar cambios»). |

---

## Qué hay en cada carpeta

| | |
|---|---|
| `README.md` | Esta guía. |
| `PERSONALIZAR.md` | Cómo ponerle la marca de la tienda. |
| `ANALISIS.md` | De dónde sale cada parte y qué no trae todavía. |
| `docs/TECNICO.md` | Detalles para quien programe. |
| `flask_app/config/negocio.py` | **El archivo que se edita**: nombre, contacto, colores, puntos. |
| `flask_app/static/img/` | Las imágenes (logo, fotos). |
| `flask_app/templates/` | Las páginas. Los textos largos de la portada están en `landing.html`. |
| `configurar.py` | Crea el `.env` de tu computador. |
| `instalar_base.py` | Arma la base de datos (nunca borra nada). |
| `crear_admin.py` | Crea o cambia una cuenta de administración. |
| `server.py` | Prende el sitio. |
| `pruebas/` | Pruebas automáticas, para quien programe. |

---

Sitio diseñado y programado por
[Sr. Jengibre](https://www.linkedin.com/in/sebapoba/).
