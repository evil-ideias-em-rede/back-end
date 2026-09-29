# Sandbox de execução

O backend usa `microsandbox==0.7.2` para executar cada comando do agente em
uma microVM efêmera. A pasta `sandbox/` da conversa é montada em `/workspace`
com leitura e escrita, sem rede. Ao fim do comando, a microVM é removida e os
arquivos permanecem em `workdirs/`.

A ferramenta restrita de Audiências sugeridas monta uma cópia temporária e
sincroniza de volta somente `planning.json` e `HTML.html`.

O host e o container precisam ter acesso funcional a `/dev/kvm`. O build do
backend gera uma imagem OCI controlada e o entrypoint a carrega no cache do
microsandbox antes de iniciar a API; não é usado o socket do Docker.
