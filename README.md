# M3O Fiber Gateway Utility

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

### Modo bridge

- Consulta do modo atual: router ou bridge.
- Ativação e desativação do modo bridge.
- Confirmação de segurança antes de qualquer alteração ao modo bridge.
- Aviso de utilização da porta LAN 4 ao ativar o modo bridge.

### Port forwarding

- Listagem de regras IPv4 existentes.
- Criação de regras de encaminhamento de portos.
- Remoção de regras existentes.


### UPnP

- Consulta do estado do UPnP.
- Ativação e desativação do UPnP.

### DNS dinâmico

- Listagem de configurações de DNS dinâmico.
- Criação de configurações DynDNS.
- Criação de configurações No-IP.
- Remoção de configurações existentes.

## Compatibilidade com modo bridge

O estado 'routerMode=1' corresponde a modo bridge
ativo e 'routerMode=0' corresponde a modo router. A ferramenta apresenta também
o valor bruto 'routerMode' no menu de bridge para facilitar validação em
firmwares diferentes.

## Predefinições

IP predefinido do router:

```text
192.168.1.254
```

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
MEO-Router-Tool.exe --command bridge-status
MEO-Router-Tool.exe --command bridge-on
MEO-Router-Tool.exe --command bridge-off
```

Quando não existem credenciais guardadas, a ferramenta solicita utilizador e
password antes de executar o comando.

As funcionalidades de port forwarding, UPnP e DNS dinâmico estão disponíveis no
menu interativo.


## Não são enviados quaisquer dados pessoais para GitHub, Cloud, Servidores externos, APIs externas ou para o Programador.

## Aviso legal

Este projeto é independente e não é afiliado, patrocinado, aprovado ou mantido pela MEO, Altice Portugal ou qualquer entidade associada.

A ferramenta comunica apenas com a interface local do router, mediante credenciais de administrador fornecidas pelo utilizador. O objetivo é automatizar operações disponíveis no próprio equipamento/router do utilizador.


Todas as marcas, nomes comerciais e referências a MEO pertencem aos respetivos proprietários e são utilizados apenas para identificação e compatibilidade.

A utilização da ferramenta é feita por conta e risco do utilizador. O autor não se responsabiliza por erros de configuração, indisponibilidade de rede, perda de acesso ao router, interrupções de serviço ou quaisquer outros efeitos resultantes da utilização da ferramenta.
