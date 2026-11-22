# Ambiente local

Este directorio contiene configuraciones y herramientas para correr el proyecto de forma local durante el desarrollo.

## `./data`
Este directorio contiene volúmenes de datos locales usados para bases de datos y otros usos similares.
Sus contenidos son ignorados por GIT y no debiesen JAMAS versionarse.


## Perfil local y túnel público

- `just local init` crea `conf/local` (ignorado por git) desde `conf/local.example`, con una `SECRET_KEY` aleatoria. No crea ningún superusuario. No existe un perfil `default` con secretos versionados.
- `just local tunnel-up` expone la app en una URL temporal `*.trycloudflare.com` (cloudflared, sin cuenta). Fuerza `DEBUG=False`, apaga el selector de cuentas, acota los hosts y **rota las claves de todas las cuentas `@localhost`**, imprimiéndolas una sola vez. El túnel apunta al frontend, así que `/-docs` no queda público.
- `just local tunnel-url` / `tunnel-logs` muestran la URL y los logs; `just local tunnel-down` cierra el túnel y restaura la configuración local.
- Las claves rotadas no se restauran al cerrar el túnel. El selector de cuentas del túnel solo lo ve un superusuario; si no existe ninguno, entra con cada cuenta de demo (la clave se imprime en `tunnel-up`).
