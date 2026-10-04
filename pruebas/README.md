# Pruebas

```bash
python server.py            # en una terminal
python pruebas/suite.py     # en otra
```

La suite revisa más de 120 comportamientos contra la app corriendo de verdad
(unos más si el `.env` de prueba tiene `SHOPIFY_WEBHOOK_SECRET`): registro, sesión, panel
de administración, redirecciones, páginas públicas, las promos de la
portada, los pedidos para retiro, la ruleta de premios, los vales, el rol vendedor (barista en el código), el manifest de la PWA y el webhook de pedidos de Shopify (con sus
reembolsos). Tarda unos veinte segundos.

Los bloques:

| | Qué mira |
|---|---|
| **C1 C2 C3** | Los tres agujeros de la auditoría — ver abajo. |
| **P** | La promo de la portada: que se pinte cuando está vigente, que la API conteste 204 cuando no hay ninguna, que el interruptor la baje sin tocar el plazo, y que el destino del botón no pueda sacar a nadie del sitio (el mismo cuidado que C3). |
| **W** | El manifest de la PWA: que sea JSON válido, que lleve el nombre del negocio y no el de la plantilla, y que los cuatro iconos que declara existan. |
| **T** | El webhook de pedidos de Shopify: que una firma inválida se rechace (401) y no guarde nada; y, solo si hay `SHOPIFY_WEBHOOK_SECRET` en el `.env` de prueba, que un aviso bien firmado se guarde con el nombre del comprador, que uno repetido no duplique el pedido, que aparezca en `/admin/pedidos`, que un reembolso posterior (`orders/updated`) marque el pedido existente sin inventar uno nuevo, y que el panel responda en los cuatro cortes de tiempo (día, semana, mes, año) sin reventar con uno inventado. |
| **K** | La carta armada desde el panel: que una categoría se cree con su slug y que renombrarla no lo cambie; que un combo vigente salga en la carta pública diciendo qué trae; que uno sin fecha de término se guarde sin fecha y se vea; que el interruptor lo saque al tiro; que no se pueda colar un producto ajeno por POST; y que el banner lea el combo marcado sin copiarlo a `promos`. Se comprueba por `/api/v1/menu` y `/api/v1/promo`, como lo vería un visitante. |
| **B** | Los pedidos para retiro: que cerrados no aparezcan en la portada y abiertos sí; que `/pedir` muestre el barrio pero no la dirección exacta (y la página del pedido sí); que el total salga de la base aunque el formulario traiga otro precio; que una franja llena, una inventada, un producto ajeno o demasiadas unidades se rechacen; que cancelar libere la franja y que un pedido ya en preparación no se cancele desde el cliente; que «Estoy afuera» llegue al panel; que entregar deje cobrado; y que un mismo celular no acapare la mañana. Deja la configuración como estaba. |
| **R** | La ruleta: que un anónimo no entre al panel ni habilite giros; que un gajo sin premio no se guarde y que el panel muestre el % real de cada premio; que habilitar dé un QR; que girar sortee un gajo válido y guarde ese mismo premio; que girar otra vez devuelva lo mismo y no vuelva a sortear; que cambiar los premios después no reescriba un giro hecho; y que un código inventado, un giro vencido, uno anulado o una petición sin el token de la página no giren. Deja los premios como estaban. |
| **E** | El rol barista: que el admin lo asigne desde Cuentas; que el barista vea solo vales y ruleta en el panel y reciba 404 en cuentas, carta y ventas; que desde Cuentas no se pueda dar el rol admin ni tocar a un admin; que el admin pueda crear un barista que nace sin contraseña y la elige con su enlace (que no sirve para recuperar contraseñas, se usa una sola vez y lo lleva directo a la barra); que crear uno con un correo existente no toque esa cuenta; y que quitarle el rol le cierre el panel en su sesión abierta. |
| **V** | Los vales: que un anónimo no entre al panel; que el barista emita un vale de regalo con vencimiento y quede a su nombre; que una gift card guarde su monto y nunca venza; que sin monto no se emita; que cualquiera vea el vale sin el botón de canjear; que un cliente con sesión no pueda canjear; que el barista canjee y quede quién y cuándo; que no se canjee dos veces ni vencido; que un evento cree la hoja con un QR por vale; que la lista tenga los dos tipos; y que el barista no vea lo vendido ni pueda anular. |
| **D** | Los destacados de la tienda: que vayan primeros dentro de su categoría sin cambiar el orden de las categorías; que no se toque la caché del catálogo de Shopify; que un anónimo no entre al panel; y que un producto inventado por POST no se destaque, con color, cinta y orden raros cayendo a valores seguros. |
| **X** | Lo propio de la tienda de tatuaje: que lo agotado siga en el catálogo marcado como agotado, que sin Shopify no haya tienda online ni carrito, que el vendedor atienda la cola de pedidos sin tocar su configuración, y que instalar la base dos veces no falle ni borre nada. |
| **H** | Humo: que las páginas públicas respondan y que el panel no se abra sin rol. |

**Tres de sus bloques existen porque fallaron.** Salieron de una auditoría de
seguridad sobre la versión anterior de este código:

- **C1** — una cuenta sin contraseña podía ser reclamada por cualquiera que se
  registrara con ese correo, heredando su rol. El esquema sembraba un
  administrador sin contraseña, así que bastaba con saber ese correo —publicado
  en el pie del sitio— para quedarse con el panel. Ahora solo se reclaman
  invitados de verdad, y el esquema no siembra ningún administrador.
- **C2** — bloquear a un cliente o quitarle el rol a un administrador no surtía
  efecto hasta que esa persona cerrara sesión, porque el rol se leía de la
  cookie. Ahora se revalida contra la base en cada página protegida.
- **C3** — cuatro formularios del panel aceptaban una URL entera en su campo
  «volver»: un redirect abierto. Ahora solo aceptan rutas del propio sitio.

Si alguna de esas tres falla después de tocar el código, el agujero volvió.

**W es la que falla al vender, no al programar.** No prueba nada del código:
prueba que la instalación esté terminada. Si W1b falla, el manifest todavía
dice «Insumos Tattoo Ejemplo»; si W2 falla, faltaron los iconos y el cliente va a ver un
cuadro con rayas en su pantalla de inicio.

**T2 a T8 se saltan solas si no hay `SHOPIFY_WEBHOOK_SECRET` configurado** —
no hay forma de firmar un aviso de prueba sin el mismo secreto que está
usando la app en marcha. Eso es normal en una instalación que todavía no usa
Shopify, o que no ha dado de alta el webhook: el total baja de 49 a 40 y no
es una falla. T1 y T9 sí corren siempre.

**Ojo:** la suite escribe y borra filas de prueba. Córrela contra tu base de
desarrollo, nunca contra la de un negocio en producción. Y reinicia la app
antes: los frenos anti fuerza bruta viven en memoria y una corrida anterior
puede dejar el contador arriba.
