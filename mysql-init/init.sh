#!/usr/bin/env bash
set -eo pipefail

DB_NAME_FROM_ENV="${MYSQL_DATABASE}"
USER_NAME_FROM_ENV="${MYSQL_USER}"
USER_PASS_FROM_ENV="${MYSQL_PASSWORD}"
ROOT_PASSWORD_FROM_ENV="${MYSQL_ROOT_PASSWORD}"

printf "⚙️ init.sh: Iniciando script de inicialización.\n"
printf "⚙️ init.sh: MYSQL_ROOT_PASSWORD para conexión: [DEFINIDA, NO SE MUESTRA]\n"
printf "⚙️ init.sh: DB (del .env) a crear/verificar: %s\n" "${DB_NAME_FROM_ENV}"
printf "⚙️ init.sh: USER (del .env) a crear/verificar: %s\n" "${USER_NAME_FROM_ENV}"
printf "⚙️ init.sh: PASSWORD para USER (del .env): [DEFINIDA, NO SE MUESTRA]\n"

if [ -z "${ROOT_PASSWORD_FROM_ENV}" ]; then
    printf "⚠️ init.sh: MYSQL_ROOT_PASSWORD (del .env) no está definida. No se puede conectar a MySQL. Saliendo.\n"
    exit 1
fi

if [ -z "${DB_NAME_FROM_ENV}" ] || [ -z "${USER_NAME_FROM_ENV}" ] || [ -z "${USER_PASS_FROM_ENV}" ]; then
    printf "⚠️ init.sh: Una o más variables (MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD del .env) no están definidas. Saltando la creación de usuario/BD por este script.\n"
    printf "⚠️ init.sh: La imagen de MySQL podría haber creado una BD/usuario basado en variables directas de docker-compose.yml si se proporcionaron.\n"
else
    printf "⚙️ init.sh: Intentando crear/verificar usuario '%s' y BD '%s' con valores del .env...\n" "${USER_NAME_FROM_ENV}" "${DB_NAME_FROM_ENV}"
    
    mysql -u root -p"${ROOT_PASSWORD_FROM_ENV}" <<-EOSQL
        CREATE DATABASE IF NOT EXISTS \`${DB_NAME_FROM_ENV}\`;
        CREATE USER IF NOT EXISTS '${USER_NAME_FROM_ENV}'@'%' IDENTIFIED BY '${USER_PASS_FROM_ENV}';
        GRANT ALL PRIVILEGES ON \`${DB_NAME_FROM_ENV}\`.* TO '${USER_NAME_FROM_ENV}'@'%';
        FLUSH PRIVILEGES;
EOSQL
    
    printf "✅ init.sh: Base de datos '%s' y usuario '%s' (del .env) configurados/verificados por script.\n" "${DB_NAME_FROM_ENV}" "${USER_NAME_FROM_ENV}"
fi

printf "⚙️ init.sh: Script de inicialización finalizado.\n"