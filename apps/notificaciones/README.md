# notificaciones

Alcance: Núcleo (§3.1). **Se construye antes que sus consumidores.**

El canal de notificaciones: un componente, dos salidas. Decide **por dónde** llega un aviso; **a quién** lo decide el enrutamiento por vínculos de `apps/unidades/`.

## Qué va aquí

- Un **puerto** con adaptadores: notificación dentro de la aplicación y correo por **SMTP**
- El adaptador de WhatsApp, **declarado y sin implementar** (§3.4)
- Credenciales del SMTP por variable de entorno, nunca en el repositorio

## Qué hay hoy

Construido el 2026-09-22 para HU-25, que es su primer consumidor.

- `canal.notificar(aviso, persona_ids)`: deja el aviso en la bandeja (`Notificacion`) y, al confirmarse la transacción, manda un correo por persona. Solo a cuentas que pueden entrar; un fallo del correo no deshace el aviso
- Un mismo hecho avisa una sola vez: `UNIQUE (persona, origen, referencia)` en la base
- `GET /notificaciones/`: los avisos de quien pregunta en el conjunto activo, los 100 más recientes
- No hay marca de leída ni adaptador de WhatsApp todavía

## Con qué se conecta

- `apps/unidades/`: recibe los destinatarios ya resueltos
- Consumidores: `reservas`, `triage`, `citas`, `infracciones`, `anuncios`, `pagos`, `visitantes`, `cuentas` y las anulaciones del Superusuario
- Frontend: `Admind_Front-End/apps/notificaciones/`

## Referencias

Maestro §3.1, §5.5 · Decisión §9: 4

## Pendiente

- No tiene HU ni story points propios (PB-08, §12.4)
