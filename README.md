# Ferramenta Router MEO

Developed by diogorafael

Pequena ferramenta interativa de consola para routers MEO Fiber Gateway.

Esta ferramenta permite consultar e alterar algumas opcoes do router diretamente
a partir do teu PC, usando a interface local do proprio router. Em alguns routers
ou firmwares, opcoes como ligar/desligar Wi-Fi ou alterar o modo bridge podem
estar pouco acessiveis na interface normal, ou obrigar a contactar o apoio
tecnico. Esta ferramenta automatiza esses pedidos localmente, sem depender do
apoio tecnico para executar essas alteracoes quando tens acesso de administrador
ao router.

A ferramenta pede o IP do router, utilizador e password. Depois mostra um menu
com:

- Estado
- Menu de Wi-Fi
- Menu de DNS
- Menu de modo bridge
- Menu de credenciais guardadas
- Ativar/desativar modo bridge com confirmacao extra de seguranca

IP default do router: `192.168.1.254`

DNS default:

- Primario: `1.1.1.1`
- Secundario: `212.55.154.190`

## Como correr

Tens duas opcoes.

### Opcao 1: EXE para Windows

Duplo clique em:

```text
MEO-Router-Tool.exe
```

Esta e a forma mais simples. Nao precisa de Python instalado.

### Opcao 2: Python, Windows/Linux/macOS

Duplo clique em:

```text
run_from_source.bat
```

Esta opcao corre o ficheiro Python diretamente e precisa de Python instalado.

Tambem podes correr manualmente:

```text
python meo_router_tool.py
```

Em Linux/macOS, usa a opcao Python. A gestao de credenciais guardadas foi feita
com a protecao do Windows, por isso essa parte so esta disponivel em Windows.

## Privacidade e dados

A ferramenta corre localmente no teu PC.

O codigo foi preparado para comunicar apenas com o IP do router que inseres no
inicio, por exemplo:

```text
http://192.168.1.254
```

Nao envia utilizador, password, configuracoes do router, DNS, estado de Wi-Fi,
modo bridge, ou qualquer outro dado pessoal para GitHub, cloud, servidores
externos, APIs externas, ou para o developer.

As credenciais sao usadas apenas para fazer login na pagina local do router. Se
escolheres guardar credenciais, elas ficam num ficheiro local encriptado pelo
Windows para o teu utilizador neste PC.

## Criar o EXE standalone

Duplo clique em:

```text
build_exe.bat
```

O script de build cria uma pasta temporaria `.venv-build`, instala o
PyInstaller, e cria:

```text
dist\MEO-Router-Tool.exe
```

Depois podes correr o `.exe` com duplo clique.

## Credenciais guardadas

Depois de um login manual com sucesso, a ferramenta pode guardar as credenciais
em:

```text
meo-router-credentials.encrypted.txt
```

O ficheiro e criado ao lado do EXE. Fica encriptado com a protecao do Windows,
por isso so deve desencriptar para o mesmo utilizador Windows no mesmo PC.

## Nota de seguranca

O modo bridge pode interromper a ligacao da rede de casa. A ferramenta pede
sempre para escreveres `YES` antes de alterar o modo bridge.

## Comandos diretos

Normalmente o EXE abre o menu. Tambem suporta comandos diretos:

```text
MEO-Router-Tool.exe --command status
MEO-Router-Tool.exe --command wifi-on
MEO-Router-Tool.exe --command wifi-off
MEO-Router-Tool.exe --command dns --primary-dns 1.1.1.1 --secondary-dns 212.55.154.190
MEO-Router-Tool.exe --command bridge-status
MEO-Router-Tool.exe --command bridge-on
MEO-Router-Tool.exe --command bridge-off
```

A ferramenta continua a pedir utilizador e password, exceto quando usas
credenciais guardadas.
