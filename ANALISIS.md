# Análisis: de la plantilla de cafetería a una tienda de insumos de tatuaje

Este documento explica **qué es esta plantilla, de dónde viene y por qué
cada parte quedó como quedó**. Sirve para entender la app antes de
instalarla, y para decidir qué encender y qué no.

---

## 1. De dónde viene

La plantilla nació como el sitio de una cafetería de especialidad: carta
digital, tienda online, talleres con inscripción, programa de puntos, ruleta
de premios, vales de regalo y un panel para administrar todo. Ese mismo
esqueleto sirve casi completo para otro negocio que también:

- vende **productos que se reponen seguido** (el café se acaba; los cartuchos
  y los guantes también),
- tiene **clientes que vuelven** y a los que vale la pena premiar,
- hace **actividades con cupo** (catas allá, capacitaciones acá),
- y atiende **en un local**, con gente detrás del mesón.

Una tienda de insumos para tatuadores calza en las cuatro.

## 2. Cómo es el negocio

| | Cafetería | Tienda de insumos de tatuaje |
|---|---|---|
| Quién compra | Público general | **Tatuadores y estudios** (venta entre profesionales) |
| Qué compra | Una bebida, para tomar ahora | Cartuchos, agujas, tintas, máquinas, fuentes de poder, bioseguridad, cuidado post-tatuaje |
| Cada cuánto | Varias veces por semana | Cada una o dos semanas: lo que se gasta en cada sesión |
| Cómo pide hoy | En el mesón | Por WhatsApp o Instagram, y retira en tienda o le despachan |
| Qué le importa | Que esté rico y rápido | **Saber si hay stock**, el precio claro, las novedades y no perder tiempo |
| Qué lo fideliza | Puntos y la experiencia | Puntos, atención, **capacitaciones** y comunidad |

Lo más importante: el cliente es un profesional que **vuelve a comprar lo
mismo**. Por eso el catálogo tiene que ser rápido de leer, decir con
claridad qué hay y qué no, y dejar pedir sin escribir un mensaje largo.

## 3. Módulo por módulo

| En la cafetería | En la tienda de tatuaje | Qué cambió |
|---|---|---|
| **Carta digital** (cafés, pasteles) | **Catálogo de insumos** | Categorías editables desde el panel: Cartuchos, Agujas, Tintas, Máquinas, Fuentes de poder, Bioseguridad, Cuidado post-tatuaje, Accesorios. Un interruptor marca lo agotado: **sigue a la vista, marcado como «Agotado»** (en la cafetería se escondía), porque al tatuador le sirve saber que existe y que vuelve. Viene con productos de ejemplo. |
| **Combos** («café + algo dulce») | **Packs y kits** | «Kit de inicio», «Pack bioseguridad semanal». Mismo funcionamiento: varios productos a un precio, con fecha de término o sin ella. |
| **Pedidos para retiro** | **Pide online y retira en tienda** | El tatuador arma su pedido desde el catálogo, elige día y hora de retiro y paga al retirar. La tienda lo ve en una cola desde el panel. Nace apagado: se enciende cuando la tienda quiera. |
| **Tienda online con Shopify** | **Igual, pero opcional y apagada** | Si la tienda ya usa Shopify, se conecta con dos datos en el `.env`. Si no, la sección no aparece (no queda ninguna maqueta a la vista). |
| **Destacados de la tienda** («micro lote») | **Lanzamientos** | Para resaltar productos de Shopify con borde de color y una cinta («Nuevo», «Edición limitada»). Solo tiene sentido con Shopify encendido. |
| **Talleres y catas** | **Cursos y capacitaciones** | Bioseguridad, técnica, color, convenciones, guest spots. Inscripción con cupos, reserva de 24 horas, comprobante de transferencia, voucher con QR y botón para agregarlo al calendario. |
| **Programa de puntos** | **Puntos Tinta** (nombre editable) | Se presenta en la portada con su equivalencia (por defecto 1 punto = $10). Los precios se muestran en pesos: mostrar precios en puntos que todavía no se pueden usar sería prometer algo que no existe (ver «Lo que no trae»). |
| **Vales y gift cards** | **Vales y gift cards** | Una gift card es un buen regalo para un tatuador. Los vales sirven para premios, sorteos o convenciones. Se canjean una sola vez, escaneando el QR. |
| **Ruleta de premios** | **Ruleta de premios** | Para compras sobre un monto: «10 % en cartuchos», «Guantes gratis», «Sigue participando». El admin escribe los premios y el servidor sortea. |
| **Muro de deseos** | **Muro de la comunidad** | Los tatuadores piden productos que quieren que la tienda traiga, recomiendan marcas o saludan. Nada se publica sin aprobación. |
| **Promos con cuenta regresiva** | **Promos** | «20 % en tintas hasta el viernes». Banner en la portada con su contador. |
| **Reseñas de Google** | **Igual** | Botón «Dejar una reseña» junto al mapa, si se configura la ficha de Google. |
| **Mascotas de temporada** | **Apagadas** | El sistema queda listo por si la tienda tiene ilustraciones propias. |
| **Rol barista** | **Rol vendedor(a)** | El personal del mesón: entra a vales, ruleta y pedidos, no al resto del panel. |
| **Segunda marca** (pizzas de noche) | **Apagada** | Útil si la tienda también tiene un estudio de tatuajes con su propia identidad. Se enciende en `negocio.py`. |
| **Panel de administración** | **Igual** | Catálogo, packs, cursos, inscripciones, promos, vales, ruleta, pedidos, cuentas y moderación del muro. |

## 4. Lo que se dejó igual a propósito

- **Toda la seguridad**: contraseñas cifradas, protección contra formularios
  falsos (CSRF), frenos contra fuerza bruta, enlaces firmados para verificar
  el correo y recuperar la contraseña, sesiones que se revalidan.
- **La regla de no mostrar botones que no funcionan**: lo que está apagado no
  aparece, en vez de llevar a una página de «próximamente».
- **El crédito del pie de página**, con su enlace y su easter egg.

## 5. Lo que NO trae (conviene decirlo antes)

- **No cobra en línea.** Los pedidos se pagan al retirar; los cursos, por
  transferencia que el admin confirma. Shopify es opcional.
- **No lleva inventario por cantidad.** Cada producto está «disponible» o
  «agotado»; no descuenta unidades al vender.
- **No hay billetera de puntos.** El programa se presenta en la portada,
  pero el saldo de cada cliente todavía no se acumula.
- **No hace despachos.** Pedidos para retirar en tienda; el envío se coordina
  por WhatsApp como hoy.
- **No emite boleta ni factura.** Eso sigue en el sistema que la tienda ya use.

## 6. Ideas para una segunda etapa

Pensadas para este rubro, no construidas:

1. **Precios por volumen**: «caja de 20 cartuchos: $X; desde 5 cajas: $Y».
2. **Cuenta de estudio**: varios tatuadores comprando a nombre de un mismo
   estudio, con un solo historial.
3. **Recordatorio de recompra**: «hace 3 semanas llevaste cartuchos RL 3;
   ¿te los dejamos listos?».
4. **Ficha técnica por producto**: compatibilidad de cartuchos con máquinas,
   registro sanitario de las tintas, tamaños de guantes.
5. **Saldo real de puntos**, con canje en el mesón.
