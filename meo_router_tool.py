#!/usr/bin/env python3
"""
Ferramenta interativa para Windows para routers MEO Fiber Gateway.

A ferramenta faz login usando o fluxo da interface web do router e mostra um
menu simples para estado, Wi-Fi, DNS e modo bridge.

Marca de agua: Developed by diogorafael
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


APP_NAME = "Ferramenta Router MEO"
WATERMARK = "Developed by diogorafael"
DEFAULT_ROUTER = "192.168.1.254"
DEFAULT_PRIMARY_DNS = "1.1.1.1"
DEFAULT_SECONDARY_DNS = "212.55.154.190"
REQUEST_TIMEOUT = 12
CREDENTIALS_FILENAME = "meo-router-credentials.encrypted.txt"


class RouterError(Exception):
    """Erro lancado quando o router rejeita ou nao conclui uma operacao."""


@dataclass
class OperationResult:
    label: str
    value: str


@dataclass
class SavedCredentials:
    router_ip: str
    username: str
    password: str


class MeoRouter:
    def __init__(self, router_ip: str) -> None:
        self.router_ip = router_ip.strip()
        self.base_url = f"http://{self.router_ip}"
        self.session = requests.Session()
        self.xsrf_token: str | None = None

        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/154.0.0.0 Safari/537.36"
                ),
            }
        )

    def login(self, username: str, password: str) -> None:
        self._initialize_session()
        nonce = self._get_nonce()
        credentials = self._calculate_credentials(username, password, nonce)

        response = self.session.get(
            f"{self.base_url}/index.html",
            headers={
                "Authorization": f"Digest {credentials}",
                "Referer": f"{self.base_url}/",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )

        if response.status_code in (401, 403):
            raise RouterError("Login falhou. Confirma o utilizador/password do router.")

        if response.status_code != 200:
            raise RouterError(f"Resposta inesperada no login: HTTP {response.status_code}")

        xsrf_token = response.headers.get("X-XSRF-TOKEN")
        if not xsrf_token:
            raise RouterError("O login resultou, mas o router nao devolveu X-XSRF-TOKEN.")

        self.xsrf_token = xsrf_token
        self.session.headers.update(
            {
                "X-XSRF-TOKEN": xsrf_token,
                "Referer": f"{self.base_url}/index.html",
            }
        )

        self.check_session()

    def check_session(self) -> None:
        response = self.session.get(
            f"{self.base_url}/fwmngt.cmd?request=check-session",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

    def get_wifi_status(self) -> bool:
        response = self.session.get(
            f"{self.base_url}/locallmngt.cmd?request=/wifi-on-off",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "estado do Wi-Fi")

        if "enableWifi" not in data:
            raise RouterError(f"Resposta inesperada do Wi-Fi: {data}")

        return bool(data["enableWifi"])

    def set_wifi_status(self, enabled: bool) -> None:
        response = self.session.put(
            f"{self.base_url}/locallmngt.cmd?request=/wifi-on-off",
            json={"enableWifi": enabled},
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": self.base_url,
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "configuracao do Wi-Fi")

        if data.get("code") not in (0, "0", None):
            raise RouterError(f"O router rejeitou a alteracao do Wi-Fi: {data}")

        time.sleep(2)
        final_status = self.get_wifi_status()
        if final_status != enabled:
            raise RouterError("O router aceitou o pedido de Wi-Fi, mas a validacao falhou.")

    def get_bridge_status(self) -> bool:
        return not self.get_router_mode()

    def get_router_mode(self) -> bool:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.lan/fgw.lan.routerMode.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "modo do router")

        router_mode = str(data.get("routerMode", "")).strip()
        if router_mode not in {"0", "1"}:
            raise RouterError(f"Nao foi possivel determinar o modo router/bridge: {data}")

        return router_mode == "1"

    def set_bridge_status(self, bridge_enabled: bool) -> None:
        current_bridge = self.get_bridge_status()
        if current_bridge == bridge_enabled:
            return

        # O endpoint chama-se bridgeMode, mas enable=1 liga o modo router
        # e enable=0 liga o modo bridge.
        enable_value = "0" if bridge_enabled else "1"

        response = self.session.get(
            f"{self.base_url}/bridgeMode.cmd",
            params={"enable": enable_value},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

        time.sleep(5)
        final_bridge = self.get_bridge_status()
        if final_bridge != bridge_enabled:
            raise RouterError("O pedido de bridge foi enviado, mas a validacao falhou.")

    def get_lan_configuration(self) -> dict[str, str]:
        data = self._get_lan_json()
        dhcp = self._find_nested_dict(data, ("dhcpServer", "dhcpServer"))
        if not dhcp:
            raise RouterError("Nao foi possivel encontrar a configuracao DHCP/LAN.")

        def value(*names: str, default: str | None = None) -> str:
            for name in names:
                if name in dhcp and dhcp[name] is not None:
                    return str(dhcp[name])
            if default is not None:
                return default
            raise RouterError(f"Nao foi possivel encontrar o campo LAN: {names[0]}")

        return {
            "dhcp_enable": value("dhcpEnable", "enblDhcpSrv"),
            "gateway": value("defaultGateway", "ethIpAddress", "LANdefaultGW"),
            "mask": value("mask", "ethSubnetMask"),
            "ip_start": value("ipStart", "dhcpEthStart"),
            "ip_end": value("ipEnd", "dhcpEthEnd"),
            "dns": value("dns", "LANdnsPrimary", default=""),
            "lease_time": value("leaseTime", "dhcpLeasedTime", default="86400"),
            "bridge": value("bridge", "brName", default="br0"),
        }

    def set_dns(self, primary_dns: str, secondary_dns: str) -> None:
        validate_ip(primary_dns, "DNS primario")
        if secondary_dns:
            validate_ip(secondary_dns, "DNS secundario")

        config = self.get_lan_configuration()
        dns_value = primary_dns if not secondary_dns else f"{primary_dns},{secondary_dns}"

        params = {
            "ethIpAddress": config["gateway"],
            "LANdefaultGW": config["gateway"],
            "ethSubnetMask": config["mask"],
            "enblDhcpSrv": config["dhcp_enable"],
            "dhcpEthStart": config["ip_start"],
            "dhcpEthEnd": config["ip_end"],
            "LANdnsPrimary": dns_value,
            "ManualDNS": "1",
            "dhcpLeasedTime": config["lease_time"],
            "brName": config["bridge"],
        }

        response = self.session.get(
            f"{self.base_url}/lancfg2.cgi?{urlencode(params)}",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

        time.sleep(2)
        final_config = self.get_lan_configuration()
        final_dns = split_dns(final_config["dns"])
        expected_dns = [primary_dns] + ([secondary_dns] if secondary_dns else [])

        if final_dns != expected_dns:
            raise RouterError(
                f"A validacao do DNS falhou. Esperado {expected_dns}, recebido {final_dns}."
            )

    def get_ipv6_status(self) -> dict[str, Any]:
        data = self._get_lan_json()
        flat = flatten_dict(data)
        return {
            "status": truthy(flat.get("ipv6Status")),
            "address": str(flat.get("ipv6Address") or ""),
            "dhcpv6": truthy(flat.get("dhcpv6Enable")),
            "slaac": truthy(flat.get("slaac")),
        }

    def collect_status(self) -> list[OperationResult]:
        results: list[OperationResult] = []

        wifi = self._safe(lambda: "ON" if self.get_wifi_status() else "OFF")
        bridge = self._safe(lambda: "BRIDGE" if self.get_bridge_status() else "ROUTER")
        lan = self._safe(self.get_lan_configuration)
        ipv6 = self._safe(self.get_ipv6_status)

        results.append(OperationResult("Wi-Fi", wifi if isinstance(wifi, str) else "Indisponivel"))
        results.append(OperationResult("Modo", bridge if isinstance(bridge, str) else "Indisponivel"))

        if isinstance(lan, dict):
            dns_values = split_dns(lan.get("dns", ""))
            results.extend(
                [
                    OperationResult("Endereco LAN", lan.get("gateway", "Indisponivel")),
                    OperationResult("DHCP", "ON" if lan.get("dhcp_enable") == "1" else "OFF"),
                    OperationResult("Inicio DHCP", lan.get("ip_start", "Indisponivel")),
                    OperationResult("Fim DHCP", lan.get("ip_end", "Indisponivel")),
                    OperationResult("DNS primario", dns_values[0] if dns_values else "Automatico"),
                    OperationResult(
                        "DNS secundario", dns_values[1] if len(dns_values) > 1 else "Nenhum"
                    ),
                ]
            )
        else:
            results.append(OperationResult("LAN/DNS", "Indisponivel"))

        if isinstance(ipv6, dict):
            results.extend(
                [
                    OperationResult("IPv6", "ON" if ipv6["status"] else "OFF"),
                    OperationResult("DHCPv6", "ON" if ipv6["dhcpv6"] else "OFF"),
                    OperationResult("SLAAC", "ON" if ipv6["slaac"] else "OFF"),
                ]
            )
            if ipv6["address"]:
                results.append(OperationResult("Endereco IPv6", ipv6["address"]))
        else:
            results.append(OperationResult("IPv6", "Indisponivel"))

        return results

    def _initialize_session(self) -> None:
        response = self.session.get(
            f"{self.base_url}/",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code not in (200, 401):
            raise RouterError(f"Nao foi possivel abrir a pagina do router: HTTP {response.status_code}")

    def _get_nonce(self) -> str:
        candidates = [
            f"{self.base_url}/uxfwk.session.loader.js",
            f"{self.base_url}/js/uxfwk.session.loader.js",
        ]

        last_error = "nao pedido"
        for url in candidates:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            last_error = f"HTTP {response.status_code}"
            if response.status_code != 200:
                continue

            match = re.search(r"nonce\s*[:=]\s*['\"]([^'\"]+)['\"]", response.text)
            if match:
                return match.group(1)

        raise RouterError(f"Nao foi possivel obter o nonce de login ({last_error}).")

    @staticmethod
    def _calculate_credentials(username: str, password: str, nonce: str) -> str:
        username_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()
        password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

        username_hmac = hmac.new(
            nonce.encode("utf-8"),
            username_hash.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        password_hmac = hmac.new(
            nonce.encode("utf-8"),
            password_hash.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

        return hashlib.sha256((username_hmac + password_hmac).encode("ascii")).hexdigest()

    def _get_lan_json(self) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.lan/fgw.lan.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        return self._response_json(response, "configuracao LAN")

    @staticmethod
    def _find_nested_dict(data: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any] | None:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        return current if isinstance(current, dict) else None

    @staticmethod
    def _response_json(response: requests.Response, label: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as error:
            raise RouterError(f"Resposta invalida em {label}: {response.text[:300]}") from error

        if not isinstance(data, dict):
            raise RouterError(f"Resposta inesperada em {label}: {data}")

        return data

    @staticmethod
    def _validate_authenticated_response(response: requests.Response) -> None:
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "desconhecido")
            raise RouterError(f"O router redirecionou para {location}. A sessao pode ter expirado.")

        if response.status_code in (401, 403):
            raise RouterError("O router rejeitou a autenticacao.")

        if not response.ok:
            raise RouterError(f"HTTP {response.status_code}: {response.text[:300]}")

    @staticmethod
    def _safe(callback: Any) -> Any:
        try:
            return callback()
        except Exception:
            return None


def split_dns(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_ip(value: str, label: str) -> None:
    try:
        ipaddress.ip_address(value)
    except ValueError as error:
        raise RouterError(f"{label} nao e um endereco IP valido: {value}") from error


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def flatten_dict(data: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(child, (dict, list)):
                    flat.setdefault(key, child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return flat


class DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def app_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def credentials_path() -> str:
    return os.path.join(app_directory(), CREDENTIALS_FILENAME)


def windows_encrypt(data: bytes) -> bytes:
    if os.name != "nt":
        raise RouterError("Guardar credenciais encriptadas so e suportado no Windows.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()

    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise RouterError("O Windows nao conseguiu encriptar as credenciais.")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def windows_decrypt(data: bytes) -> bytes:
    if os.name != "nt":
        raise RouterError("Credenciais guardadas so sao suportadas no Windows.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise RouterError("O Windows nao conseguiu desencriptar as credenciais guardadas.")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def save_credentials(credentials: SavedCredentials) -> None:
    payload = {
        "router_ip": credentials.router_ip,
        "username": credentials.username,
        "password": credentials.password,
    }
    plaintext = json.dumps(payload).encode("utf-8")
    encrypted = base64.b64encode(windows_encrypt(plaintext)).decode("ascii")

    with open(credentials_path(), "w", encoding="ascii") as file:
        file.write(encrypted)
        file.write("\n")


def load_credentials() -> SavedCredentials | None:
    path = credentials_path()
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="ascii") as file:
            encrypted = base64.b64decode(file.read().strip())

        payload = json.loads(windows_decrypt(encrypted).decode("utf-8"))
        return SavedCredentials(
            router_ip=str(payload["router_ip"]),
            username=str(payload["username"]),
            password=str(payload["password"]),
        )
    except Exception:
        return None


def delete_saved_credentials() -> None:
    path = credentials_path()
    if os.path.exists(path):
        os.remove(path)


def clear_screen() -> None:
    print("\n" * 2)


def pause() -> None:
    input("\nCarrega Enter para continuar...")


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def print_header() -> None:
    print("=" * 52)
    print(APP_NAME)
    print(WATERMARK)
    print("=" * 52)


def print_status(router: MeoRouter) -> None:
    print("\nEstado do router")
    print("-" * 52)
    for item in router.collect_status():
        print(f"{item.label + ':':16} {item.value}")


def confirm_bridge_change(current_bridge: bool, desired_bridge: bool) -> bool:
    print("\nCONFIRMACAO DE SEGURANCA")
    print("-" * 52)
    print(f"Modo atual:      {'BRIDGE' if current_bridge else 'ROUTER'}")
    print(f"Modo pedido:     {'BRIDGE' if desired_bridge else 'ROUTER'}")
    print()
    print("Alterar o modo bridge pode interromper a rede de casa.")
    print("Continua apenas se tiveres a certeza.")
    print()
    return input("Escreve YES para continuar: ").strip() == "YES"


def connect_with_credentials(credentials: SavedCredentials) -> MeoRouter:
    router = MeoRouter(credentials.router_ip)
    print("\nA fazer login...")
    router.login(username=credentials.username, password=credentials.password)
    print("Login concluido.")
    return router


def ask_credentials(router_ip: str | None = None) -> SavedCredentials:
    router_ip = router_ip or ask(
        "IP do router - carrega Enter para usar o default, ou escreve outro IP",
        DEFAULT_ROUTER,
    )
    username = ask("Utilizador")
    if not username:
        raise RouterError("O utilizador nao pode ficar vazio.")

    password = getpass.getpass("Password do router: ")
    if not password:
        raise RouterError("A password nao pode ficar vazia.")

    return SavedCredentials(router_ip=router_ip, username=username, password=password)


def maybe_save_credentials(credentials: SavedCredentials) -> None:
    answer = input("\nGuardar credenciais encriptadas para a proxima vez? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        return

    save_credentials(credentials)
    print("\nCredenciais encriptadas guardadas.")
    print(f"Ficheiro: {credentials_path()}")
    print("Estao protegidas pelo Windows para este utilizador neste PC.")


def connect_interactively(router_ip: str | None = None) -> MeoRouter:
    print_header()

    saved = None if router_ip else load_credentials()
    while saved:
        print("\nCredenciais guardadas encontradas")
        print("-" * 52)
        print(f"Ficheiro:  {credentials_path()}")
        print("Seguranca: encriptadas pelo Windows para este utilizador neste PC")
        print(f"IP router: {saved.router_ip}")
        print(f"Utilizador:{saved.username}")
        print()
        print("  1 - Usar credenciais guardadas")
        print("  2 - Introduzir credenciais diferentes")
        print("  3 - Apagar credenciais guardadas")
        print("  0 - Sair")

        choice = input("\nOption: ").strip()
        if choice == "1":
            return connect_with_credentials(saved)
        if choice == "2":
            break
        if choice == "3":
            delete_saved_credentials()
            print("Credenciais guardadas apagadas.")
            saved = None
            break
        if choice == "0":
            raise KeyboardInterrupt

        print("Escolhe uma opcao valida.")

    credentials = ask_credentials(router_ip)
    router = connect_with_credentials(credentials)
    maybe_save_credentials(credentials)
    return router


def interactive_menu(router: MeoRouter) -> int:
    while True:
        print("\nO que queres fazer?")
        print("  1 - Ver estado")
        print("  2 - Wi-Fi")
        print("  3 - DNS")
        print("  4 - Modo bridge")
        print("  5 - Credenciais guardadas")
        print("  0 - Sair")

        choice = input("\nOption: ").strip()

        try:
            if choice == "1":
                print_status(router)
                pause()
            elif choice == "2":
                wifi_menu(router)
            elif choice == "3":
                dns_menu(router)
            elif choice == "4":
                bridge_menu(router)
            elif choice == "5":
                credentials_menu()
            elif choice == "0":
                print("Ate ja.")
                return 0
            else:
                print("Escolhe uma opcao valida.")
        except RouterError as error:
            print(f"\nERRO: {error}")
            pause()
        except requests.RequestException as error:
            print(f"\nERRO DE REDE: {error}")
            pause()


def wifi_menu(router: MeoRouter) -> None:
    while True:
        print("\nWi-Fi")
        print("-" * 52)
        print("  1 - Ver estado do Wi-Fi")
        print("  2 - Ligar Wi-Fi")
        print("  3 - Desligar Wi-Fi")
        print("  0 - Voltar")

        choice = input("\nOption: ").strip()
        if choice == "1":
            print(f"\nWi-Fi: {'ON' if router.get_wifi_status() else 'OFF'}")
            pause()
        elif choice == "2":
            change_wifi(router, True)
            pause()
        elif choice == "3":
            change_wifi(router, False)
            pause()
        elif choice == "0":
            return
        else:
            print("Escolhe uma opcao valida.")


def dns_menu(router: MeoRouter) -> None:
    while True:
        print("\nDNS")
        print("-" * 52)
        print("  1 - Ver DNS atual")
        print("  2 - Definir DNS")
        print("  0 - Voltar")

        choice = input("\nOption: ").strip()
        if choice == "1":
            current = router.get_lan_configuration()
            print(f"\nDNS atual: {current.get('dns') or 'automatico'}")
            pause()
        elif choice == "2":
            change_dns(router)
            pause()
        elif choice == "0":
            return
        else:
            print("Escolhe uma opcao valida.")


def bridge_menu(router: MeoRouter) -> None:
    while True:
        print("\nModo bridge")
        print("-" * 52)
        print("  1 - Ver estado do bridge")
        print("  2 - Ativar modo bridge")
        print("  3 - Desativar modo bridge")
        print("  0 - Voltar")

        choice = input("\nOption: ").strip()
        if choice == "1":
            show_bridge_status(router)
            pause()
        elif choice == "2":
            change_bridge(router, True)
            pause()
        elif choice == "3":
            change_bridge(router, False)
            pause()
        elif choice == "0":
            return
        else:
            print("Escolhe uma opcao valida.")


def credentials_menu() -> None:
    while True:
        saved = load_credentials()
        print("\nCredenciais guardadas")
        print("-" * 52)
        if saved:
            print(f"Ficheiro:  {credentials_path()}")
            print("Seguranca: encriptadas pelo Windows para este utilizador neste PC")
            print(f"IP router: {saved.router_ip}")
            print(f"Utilizador:{saved.username}")
        else:
            print("Nao ha credenciais guardadas.")
        print()
        print("  1 - Apagar credenciais guardadas")
        print("  0 - Voltar")

        choice = input("\nOption: ").strip()
        if choice == "1":
            delete_saved_credentials()
            print("Credenciais guardadas apagadas.")
            pause()
        elif choice == "0":
            return
        else:
            print("Escolhe uma opcao valida.")


def change_wifi(router: MeoRouter, enabled: bool) -> None:
    current = router.get_wifi_status()
    print(f"\nWi-Fi atual: {'ON' if current else 'OFF'}")
    if current == enabled:
        print("Nao e preciso alterar.")
        return

    router.set_wifi_status(enabled)
    print(f"O Wi-Fi esta agora {'ON' if enabled else 'OFF'}.")


def change_dns(router: MeoRouter, primary: str | None = None, secondary: str | None = None) -> None:
    current = router.get_lan_configuration()
    print(f"\nDNS atual: {current.get('dns') or 'automatico'}")

    primary = primary or ask("DNS primario", DEFAULT_PRIMARY_DNS)
    secondary = secondary if secondary is not None else ask("DNS secundario", DEFAULT_SECONDARY_DNS)

    print(f"\nNovo DNS: {primary}" + (f", {secondary}" if secondary else ""))
    answer = input("Aplicar esta configuracao de DNS? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.set_dns(primary_dns=primary, secondary_dns=secondary)
    print("Configuracao de DNS atualizada e validada.")


def show_bridge_status(router: MeoRouter) -> None:
    bridge = router.get_bridge_status()
    print(f"\nModo: {'BRIDGE' if bridge else 'ROUTER'}")


def change_bridge(router: MeoRouter, bridge_enabled: bool) -> None:
    current_bridge = router.get_bridge_status()
    if current_bridge == bridge_enabled:
        print(f"\nJa esta em modo {'BRIDGE' if bridge_enabled else 'ROUTER'}.")
        return

    if not confirm_bridge_change(current_bridge, bridge_enabled):
        print("Cancelado.")
        return

    print("\nA alterar o modo do router...")
    router.set_bridge_status(bridge_enabled)
    print(f"O modo agora e {'BRIDGE' if bridge_enabled else 'ROUTER'}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ferramenta interativa para router MEO.",
        add_help=False,
    )
    parser._optionals.title = "opcoes"
    parser.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")
    parser.add_argument("--router", default=None, help=f"IP do router. Predefinicao: {DEFAULT_ROUTER}")
    parser.add_argument(
        "--command",
        choices=["menu", "status", "wifi-on", "wifi-off", "dns", "bridge-status", "bridge-on", "bridge-off"],
        default="menu",
        help="Comando direto opcional. Por predefinicao abre o menu.",
    )
    parser.add_argument("--primary-dns", default=DEFAULT_PRIMARY_DNS)
    parser.add_argument("--secondary-dns", default=DEFAULT_SECONDARY_DNS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        router = connect_interactively(args.router)

        if args.command == "menu":
            return interactive_menu(router)
        if args.command == "status":
            print_status(router)
            return 0
        if args.command == "wifi-on":
            change_wifi(router, True)
            return 0
        if args.command == "wifi-off":
            change_wifi(router, False)
            return 0
        if args.command == "dns":
            change_dns(router, args.primary_dns, args.secondary_dns)
            return 0
        if args.command == "bridge-status":
            show_bridge_status(router)
            return 0
        if args.command == "bridge-on":
            change_bridge(router, True)
            return 0
        if args.command == "bridge-off":
            change_bridge(router, False)
            return 0

        parser.error("Comando desconhecido.")
        return 2
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
    except RouterError as error:
        print(f"\nERRO: {error}")
        return 1
    except requests.RequestException as error:
        print(f"\nERRO DE REDE: {error}")
        return 1
    except Exception as error:
        print(f"\nERRO INESPERADO: {error}")
        return 1
    finally:
        if getattr(sys, "frozen", False):
            input("\nCarrega Enter para fechar...")


if __name__ == "__main__":
    raise SystemExit(main())
