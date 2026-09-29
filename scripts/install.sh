#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

die() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
case "${1:-}" in
  ''|--check) ;;
  *) die 'Uso: bash scripts/install.sh [--check]' ;;
esac

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || die 'Esta instalação suporta Linux x86_64 com KVM. Use uma VM Linux com virtualização aninhada em outros sistemas.'
[[ -c /dev/kvm ]] || die '/dev/kvm não encontrado. Ative a virtualização na BIOS/UEFI e configure KVM antes de instalar.'
command -v docker >/dev/null || die 'Instale Docker Engine e o plugin Docker Compose v2.'
docker info >/dev/null 2>&1 || die 'Docker indisponível ou sem permissão. Confira o daemon e as permissões do seu usuário.'
docker compose version >/dev/null 2>&1 || die 'Instale o plugin Docker Compose v2.'
[[ -f ../front-end/package-lock.json ]] || die 'Clone front-end ao lado de back-end, mantendo esses nomes de pasta.'
[[ -s graph/tools/retrieval/public_hearing/PublicHearingBR_LDS.jsonl ]] || die 'Dataset base ausente. Obtenha a distribuição completa do projeto.'
[[ -s graph/tools/retrieval/dados_camara/resultados_mimo_corpus/resultados_mimo_corpus.csv.gz ]] || die 'Corpus anotado ausente. Obtenha a distribuição completa do projeto; consulte README.md.'

if [[ "${1:-}" == --check ]]; then
  printf 'Pré-requisitos locais encontrados. A disponibilidade do provedor LLM será verificada no uso.\n'
  exit 0
fi

if [[ ! -e .env.install ]]; then
  umask 077
  postgres_password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  jwt_secret="$(od -An -N48 -tx1 /dev/urandom | tr -d ' \n')"
  # noclobber também protege contra outra execução simultânea do instalador.
  ( set -o noclobber
    sed -e "s/GENERATE_POSTGRES_PASSWORD/${postgres_password}/" \
        -e "s/GENERATE_JWT_SECRET/${jwt_secret}/" \
        .env.install.example > .env.install
  )
  unset postgres_password jwt_secret
  printf 'Criado .env.install com segredos exclusivos (permissão 600).\nEscolha LLM_PROVIDER e preencha a chave/modelo desse provedor; mantenha OPENAI_API_KEY para embeddings. Execute este comando novamente.\n'
  exit 0
fi

# Não carrega o arquivo como script de shell e não exibe os segredos.
compose=(docker compose --env-file .env.install -f compose.install.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait --wait-timeout 900
printf '\nInstalação pronta. Porta publicada:\n'
"${compose[@]}" port frontend 8080
printf 'Abra esse endereço no navegador e crie sua conta por e-mail.\n'
