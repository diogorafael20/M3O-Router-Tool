# Ferramenta Router MEO para Windows

Developed by diogorafael

Pequena ferramenta interativa de consola para routers MEO Fiber Gateway.

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

## Correr a partir do codigo

Duplo clique em:

```text
run_from_source.bat
```

Precisa de Python instalado.

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
