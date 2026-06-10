# Código base

Este directorio contiene el código base que se utilizó para crear la solución incluida en este repositorio.

El código fue tomado de:

https://github.com/remzi-arpacidusseau/ostep-projects

Referencias y licencia: consulte el repositorio original para los términos de uso.

## Descripción del servidor monohilo

Breve explicación del servidor monohilo usado como base:

- Flujo: el servidor abre un socket, hace `bind()` y `listen()`, y entra en un bucle que llama a `accept()`; por cada conexión aceptada lee la petición, procesa y escribe la respuesta, cierra la conexión y vuelve a `accept()`.
- Parseo de petición: `request.c` extrae método, ruta y headers para decidir la respuesta.
- E/S bloqueante: las operaciones de lectura/escritura usan llamadas bloqueantes (helpers en `io_helper.c`), por lo que mientras atiende un cliente no puede atender otros.
- Respuesta: suele leer el recurso (archivo) y enviar encabezados HTTP + cuerpo al socket antes de cerrar.
- Limitaciones: simple y fácil de entender pero no escala con muchos clientes; sufre head-of-line blocking y es vulnerable a conexiones lentas.
- Mejoras posibles: multi-proceso/multi-hilo, pool de workers, o I/O no bloqueante (`select`/`poll`/`epoll`).

Para ver la implementación, consulte: [concurrency-webserver/src/CodeBase/wserver.c](concurrency-webserver/src/CodeBase/wserver.c#L1), [concurrency-webserver/src/CodeBase/request.c](concurrency-webserver/src/CodeBase/request.c#L1), y [concurrency-webserver/src/CodeBase/io_helper.c](concurrency-webserver/src/CodeBase/io_helper.c#L1).
