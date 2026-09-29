#!/usr/bin/env bash
set -euo pipefail

# `workdirs` é um bind mount do host. Ao ser criado por sudo/Docker, ele pode
# ficar pertencendo ao root e impedir que a API (UID/GID do host) abra novas
# sessões. Preparamos o mount como root e só então reduzimos privilégios.
APP_UID="${BACKEND_UID:-1000}"
APP_GID="${BACKEND_GID:-1000}"
INDEX_DIR="/app/graph/tools/retrieval/indice"
MICROSANDBOX_DIR="${MSB_HOME:-/app/microsandbox}"

# O container inicia como root, mas o servidor é reduzido para APP_UID.
# Evita que clientes PostgreSQL tentem acessar /root/.postgresql.
export HOME=/tmp

mkdir -p /app/workdirs
mkdir -p "${INDEX_DIR}"
mkdir -p "${MICROSANDBOX_DIR}"

python -m services.install_config
if [[ ! -c /dev/kvm ]]; then
  echo "Erro: /dev/kvm indisponível. Este backend requer Linux com KVM funcional." >&2
  exit 1
fi
python -m services.install_index

chown "${APP_UID}:${APP_GID}" /app/workdirs
chown -R "${APP_UID}:${APP_GID}" "${INDEX_DIR}"
chown -R "${APP_UID}:${APP_GID}" "${MICROSANDBOX_DIR}"
# Alguns bind mounts recusam chmod mesmo quando já estão com o modo correto.
# Isso não deve impedir a API de iniciar após a posse ter sido corrigida.
chmod 0755 /app/workdirs 2>/dev/null || true
# Garante leitura/escrita para o usuário da aplicação nos workdirs já
# existentes. Diretórios também precisam do bit de execução para permitir
# navegação e criação de arquivos.
find /app/workdirs -type d -exec chmod u+rwx {} + 2>/dev/null || true
find /app/workdirs -type f -exec chmod u+rw {} + 2>/dev/null || true

SANDBOX_GROUP_ARGS=(--clear-groups)
if [[ -e /dev/kvm ]]; then
  SANDBOX_GROUP_ARGS=(--groups "$(stat -c '%g' /dev/kvm)")
fi

echo "Preparando imagem do microsandbox..."
setpriv \
  --reuid="${APP_UID}" \
  --regid="${APP_GID}" \
  "${SANDBOX_GROUP_ARGS[@]}" \
  python -m sandbox.ensure_image

exec setpriv \
  --reuid="${APP_UID}" \
  --regid="${APP_GID}" \
  "${SANDBOX_GROUP_ARGS[@]}" \
  "$@"
