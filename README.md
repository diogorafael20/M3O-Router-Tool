# Ferramenta Router MEO

Developed by diogorafael

Ferramenta de consola para gestão local de routers MEO Fiber Gateway.

O projeto permite consultar e alterar definições do router diretamente a partir
do computador do utilizador, através da interface local do equipamento. Em
alguns modelos ou versões de firmware, operações como ligar/desligar o Wi-Fi ou
alterar o modo bridge podem não estar facilmente disponíveis na interface
normal, ou podem exigir contacto com o apoio técnico. Esta ferramenta automatiza
esses pedidos localmente, desde que o utilizador tenha credenciais de
administrador do router.

## Funcionalidades

### Estado e autenticação

- Login local no router através das credenciais de administrador.
- Consulta do estado geral do router.
- Armazenamento opcional de credenciais encriptadas em Windows.
- Execução através de `.exe` em Windows ou diretamente por Python.

### Wi-Fi

- Consulta do estado do Wi-Fi.
- Ativação e desativação do Wi-Fi.

### DNS

- Consulta do DNS configurado no router.
- Configuração manual de DNS primário e secundário.
- Presets rápidos:
  - Cloudflare: `1.1.1.1` / `1.0.0.1`
  - Google: `8.8.8.8` / `8.8.4.4`
  - Quad9: `9.9.9.9` / `149.112.112.112`
  - MEO: `212.55.154.190` / `212.55.154.174`

### Modo bridge

- Consulta do modo atual: router ou bridge.
- Apresentação do valor bruto `routerMode` devolvido pelo router.
- Ativação e desativação do modo bridge.
- Confirmação de segurança antes de qualquer alteração ao modo bridge.
- Aviso de utilização da porta LAN 4 ao ativar o modo bridge.

### Port forwarding

- Listagem de regras IPv4 existentes.
- Criação de regras de encaminhamento de portos.
- Remoção de regras existentes.
- Suporte para TCP, UDP e TCP/UDP.

### UPnP

- Consulta do estado do UPnP.
- Ativação e desativação do UPnP.

### DNS dinâmico

- Listagem de configurações de DNS dinâmico.
- Criação de configurações DynDNS.
- Criação de configurações No-IP.
- Remoção de configurações existentes.

## Compatibilidade com modo bridge

Nos routers testados, o estado local `routerMode=1` corresponde a modo bridge
ativo e `routerMode=0` corresponde a modo router. A ferramenta apresenta também
o valor bruto `routerMode` no menu de bridge para facilitar validação em
firmwares diferentes.

## Predefinições

IP predefinido do router:

```text
192.168.1.254
```

DNS predefinido:

```text
Primário:   1.1.1.1
Secundário: 212.55.154.190
```

## Tecnologias utilizadas

- Python 3
- `requests`, para comunicação HTTP com a interface local do router
- Windows DPAPI, para encriptação local de credenciais em Windows
- PyInstaller, para geração do executável standalone
- GitHub Actions, para validação do projeto e geração de artefactos

## Execução

### Windows, através do executável

Executar:

```text
MEO-Router-Tool.exe
```

Esta é a opção recomendada em Windows, pois não requer instalação manual de
Python.

Também é disponibilizado um pacote `.zip` com o executável, código-fonte,
scripts e documentação:

```text
MEO-Router-Tool-Windows.zip
```

### Python, Windows/Linux/macOS

Executar:

```text
python meo_router_tool.py
```

Em Windows, também é possível usar:

```text
run_from_source.bat
```

Em Linux/macOS, deve ser usada a execução por Python. A funcionalidade de
credenciais guardadas foi implementada com Windows DPAPI, pelo que está
disponível apenas em Windows.

## Privacidade e dados

A ferramenta corre localmente no computador do utilizador.

O código comunica apenas com o IP do router indicado no início da execução, por
exemplo:

```text
http://192.168.1.254
```

Não são enviados utilizador, password, configurações do router, DNS, estado de
Wi-Fi, modo bridge ou quaisquer outros dados pessoais para GitHub, cloud,
servidores externos, APIs externas ou para o programador.

As credenciais são usadas apenas para autenticação na página local do router. Se
o utilizador optar por guardar credenciais, estas ficam num ficheiro local
encriptado pelo Windows para o utilizador atual do sistema.

## Credenciais guardadas

Após um login manual bem-sucedido, a ferramenta pode guardar credenciais em:

```text
meo-router-credentials.encrypted.txt
```

O ficheiro é criado na mesma pasta do executável. Em Windows, as credenciais são
encriptadas com a proteção do próprio sistema operativo e deverão ser
desencriptáveis apenas pelo mesmo utilizador no mesmo computador.

## Segurança e responsabilidade

A alteração do modo bridge pode interromper a ligação da rede local. Por esse
motivo, a ferramenta exige confirmação explícita com `YES` antes de executar
qualquer alteração ao modo bridge.

Ao ativar o modo bridge, a porta LAN 4 passa a ser usada para bridge, conforme
indicado na interface do router MEO.

A utilização desta ferramenta é feita por conta e risco do utilizador. O autor
não se responsabiliza por erros de configuração, indisponibilidade de rede,
perda de acesso ao router, interrupções de serviço ou quaisquer outros efeitos
resultantes da utilização da ferramenta.

As funcionalidades de port forwarding, UPnP e DNS dinâmico alteram diretamente
exposição e encaminhamento de serviços na rede. Devem ser usadas apenas quando o
utilizador compreende o impacto de cada alteração.

## Criar o executável

Executar:

```text
build_exe.bat
```

O script cria um ambiente local de build, instala as dependências necessárias e
gera:

```text
dist\MEO-Router-Tool.exe
```

## Comandos diretos

A maioria das funcionalidades está disponível através do menu interativo. Além
do menu, a ferramenta suporta alguns comandos diretos:

```text
MEO-Router-Tool.exe --command status
MEO-Router-Tool.exe --command wifi-on
MEO-Router-Tool.exe --command wifi-off
MEO-Router-Tool.exe --command dns --primary-dns 1.1.1.1 --secondary-dns 212.55.154.190
MEO-Router-Tool.exe --command bridge-status
MEO-Router-Tool.exe --command bridge-on
MEO-Router-Tool.exe --command bridge-off
```

Quando não existem credenciais guardadas, a ferramenta solicita utilizador e
password antes de executar o comando.

As funcionalidades de port forwarding, UPnP e DNS dinâmico estão disponíveis no
menu interativo.
