#!/usr/bin/env python3
"""
Ferramenta interativa para routers MEO Fiber Gateway.

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
import html
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
PROTOCOLS = {"1": ("TCP", "1"), "2": ("UDP", "2"), "3": ("TCP/UDP", "0")}
DDNS_PROVIDERS = {"1": ("DynDNS", "1"), "2": ("No-IP", "2")}


class RouterError(Exception):
    """Erro lançado quando o router rejeita ou não conclui uma operação."""


@dataclass
class OperationResult:
    label: str
    value: str


@dataclass
class SavedCredentials:
    router_ip: str
    username: str
    password: str


@dataclass
class PortForwardEntry:
    name: str
    external_start: str
    external_end: str
    protocol: str
    internal_start: str
    internal_end: str
    server_ip: str
    interface: str
    remove_token: str


@dataclass
class DdnsEntry:
    hostname: str
    username: str
    provider: str
    interface: str
    status: str
    remove_token: str


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
            raise RouterError("O login resultou, mas o router não devolveu X-XSRF-TOKEN.")

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
        data = self._response_json(response, "configuração do Wi-Fi")

        if data.get("code") not in (0, "0", None):
            raise RouterError(f"O router rejeitou a alteração do Wi-Fi: {data}")

        time.sleep(2)
        final_status = self.get_wifi_status()
        if final_status != enabled:
            raise RouterError("O router aceitou o pedido de Wi-Fi, mas a validação falhou.")

    def get_bridge_status(self) -> bool:
        return self.get_router_mode_flag() == "1"

    def get_router_mode_flag(self) -> str:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.lan/fgw.lan.routerMode.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "modo do router")

        router_mode = str(data.get("routerMode", "")).strip()
        if router_mode not in {"0", "1"}:
            raise RouterError(f"Não foi possível determinar o modo router/bridge: {data}")

        return router_mode

    def set_bridge_status(self, bridge_enabled: bool) -> None:
        current_bridge = self.get_bridge_status()
        if current_bridge == bridge_enabled:
            return

        enable_value = "1" if bridge_enabled else "0"

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
            raise RouterError("O pedido de bridge foi enviado, mas a validação falhou.")

    def get_lan_configuration(self) -> dict[str, str]:
        data = self._get_lan_json()
        dhcp = self._find_nested_dict(data, ("dhcpServer", "dhcpServer"))
        if not dhcp:
            raise RouterError("Não foi possível encontrar a configuração DHCP/LAN.")

        def value(*names: str, default: str | None = None) -> str:
            for name in names:
                if name in dhcp and dhcp[name] is not None:
                    return str(dhcp[name])
            if default is not None:
                return default
            raise RouterError(f"Não foi possível encontrar o campo LAN: {names[0]}")

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
        validate_ip(primary_dns, "DNS primário")
        if secondary_dns:
            validate_ip(secondary_dns, "DNS secundário")

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
                f"A validação do DNS falhou. Esperado {expected_dns}, recebido {final_dns}."
            )

    def get_upnp_status(self) -> bool:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.contents/fgw.contents.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "estado UPnP")
        return str(data.get("upnp", "0")).strip() == "1"

    def set_upnp_status(self, enabled: bool) -> None:
        response = self.session.get(
            f"{self.base_url}/upnpcfg.cgi",
            params={"enblUpnp": "1" if enabled else "0"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

        time.sleep(2)
        final_status = self.get_upnp_status()
        if final_status != enabled:
            raise RouterError("O pedido de UPnP foi enviado, mas a validação falhou.")

    def get_port_forward_entries(self) -> list[PortForwardEntry]:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.security/fgw.natv4.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "regras de port forwarding")
        return parse_port_forward_entries(str(data.get("portForwarding") or ""))

    def add_port_forward(
        self,
        name: str,
        server_ip: str,
        protocol: str,
        external_start: str,
        external_end: str,
        internal_start: str,
        internal_end: str,
    ) -> None:
        validate_ip(server_ip, "IP interno")
        for label, value in {
            "porta externa inicial": external_start,
            "porta externa final": external_end,
            "porta interna inicial": internal_start,
            "porta interna final": internal_end,
        }.items():
            validate_port(value, label)

        response = self.session.get(
            f"{self.base_url}/scvrtsrv.cmd",
            params={
                "action": "add",
                "srvName": name,
                "dstWanIf": "erouter0",
                "srvAddr": server_ip,
                "proto": f"{protocol},",
                "eStart": f"{external_start},",
                "eEnd": f"{external_end},",
                "iStart": f"{internal_start},",
                "iEnd": f"{internal_end},",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

        time.sleep(2)
        entries = self.get_port_forward_entries()
        if not any(entry.name == name and entry.server_ip == server_ip for entry in entries):
            raise RouterError("A regra foi enviada, mas não apareceu na validação.")

    def remove_port_forward(self, remove_token: str) -> None:
        response = self.session.get(
            f"{self.base_url}/scvrtsrv.cmd",
            params={"action": "remove", "rmLst": remove_token},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

    def get_ddns_entries(self) -> list[DdnsEntry]:
        response = self.session.get(
            f"{self.base_url}/ss-json/fgw.contents/fgw.contents.dyndns.json",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)
        data = self._response_json(response, "DNS dinâmico")
        return parse_ddns_entries(str(data.get("dyn") or ""))

    def add_ddns(self, provider: str, username: str, password: str, hostname: str) -> None:
        response = self.session.get(
            f"{self.base_url}/ddnsmngr.cmd",
            params={
                "action": "add",
                "service": provider,
                "username": username,
                "password": password,
                "hostname": hostname,
                "iface": "erouter0",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

        time.sleep(2)
        entries = self.get_ddns_entries()
        if not any(entry.hostname == hostname for entry in entries):
            raise RouterError("A configuração DDNS foi enviada, mas não apareceu na validação.")

    def remove_ddns(self, hostname: str) -> None:
        response = self.session.get(
            f"{self.base_url}/ddnsmngr.cmd",
            params={"action": "remove", "rmLst": hostname},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        self._validate_authenticated_response(response)

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

        results.append(OperationResult("Wi-Fi", wifi if isinstance(wifi, str) else "Indisponível"))
        results.append(OperationResult("Modo", bridge if isinstance(bridge, str) else "Indisponível"))

        if isinstance(lan, dict):
            dns_values = split_dns(lan.get("dns", ""))
            results.extend(
                [
                    OperationResult("Endereço LAN", lan.get("gateway", "Indisponível")),
                    OperationResult("DHCP", "ON" if lan.get("dhcp_enable") == "1" else "OFF"),
                    OperationResult("Início DHCP", lan.get("ip_start", "Indisponível")),
                    OperationResult("Fim DHCP", lan.get("ip_end", "Indisponível")),
                    OperationResult("DNS primário", dns_values[0] if dns_values else "Automático"),
                    OperationResult(
                        "DNS secundário", dns_values[1] if len(dns_values) > 1 else "Nenhum"
                    ),
                ]
            )
        else:
            results.append(OperationResult("LAN/DNS", "Indisponível"))

        if isinstance(ipv6, dict):
            results.extend(
                [
                    OperationResult("IPv6", "ON" if ipv6["status"] else "OFF"),
                    OperationResult("DHCPv6", "ON" if ipv6["dhcpv6"] else "OFF"),
                    OperationResult("SLAAC", "ON" if ipv6["slaac"] else "OFF"),
                ]
            )
            if ipv6["address"]:
                results.append(OperationResult("Endereço IPv6", ipv6["address"]))
        else:
            results.append(OperationResult("IPv6", "Indisponível"))

        return results

    def _initialize_session(self) -> None:
        response = self.session.get(
            f"{self.base_url}/",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code not in (200, 401):
            raise RouterError(f"Não foi possível abrir a página do router: HTTP {response.status_code}")

    def _get_nonce(self) -> str:
        candidates = [
            f"{self.base_url}/uxfwk.session.loader.js",
            f"{self.base_url}/js/uxfwk.session.loader.js",
        ]

        last_error = "não pedido"
        for url in candidates:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            last_error = f"HTTP {response.status_code}"
            if response.status_code != 200:
                continue

            match = re.search(r"nonce\s*[:=]\s*['\"]([^'\"]+)['\"]", response.text)
            if match:
                return match.group(1)

        raise RouterError(f"Não foi possível obter o nonce de login ({last_error}).")

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
        return self._response_json(response, "configuração LAN")

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
            raise RouterError(f"Resposta inválida em {label}: {response.text[:300]}") from error

        if not isinstance(data, dict):
            raise RouterError(f"Resposta inesperada em {label}: {data}")

        return data

    @staticmethod
    def _validate_authenticated_response(response: requests.Response) -> None:
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "desconhecido")
            raise RouterError(f"O router redirecionou para {location}. A sessão pode ter expirado.")

        if response.status_code in (401, 403):
            raise RouterError("O router rejeitou a autenticação.")

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


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def html_table_rows(value: str) -> list[tuple[list[str], str]]:
    rows: list[tuple[list[str], str]] = []
    for row in re.findall(r"<tr\b.*?</tr>", value, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            strip_html(cell)
            for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        ]
        token_match = re.search(
            r"name=['\"]rml['\"][^>]*value=['\"]([^'\"]+)['\"]",
            row,
            flags=re.IGNORECASE | re.DOTALL,
        )
        rows.append((cells, html.unescape(token_match.group(1)) if token_match else ""))
    return rows


def protocol_label(value: str) -> str:
    return {"0": "TCP/UDP", "1": "TCP", "2": "UDP"}.get(str(value), str(value))


def parse_port_forward_entries(value: str) -> list[PortForwardEntry]:
    entries: list[PortForwardEntry] = []
    for cells, remove_token in html_table_rows(value):
        if len(cells) < 8:
            continue
        entries.append(
            PortForwardEntry(
                name=cells[0],
                external_start=cells[1],
                external_end=cells[2],
                protocol=protocol_label(cells[3]),
                internal_start=cells[4],
                internal_end=cells[5],
                server_ip=cells[6],
                interface=cells[7],
                remove_token=remove_token,
            )
        )
    return entries


def parse_ddns_entries(value: str) -> list[DdnsEntry]:
    entries: list[DdnsEntry] = []
    for cells, remove_token in html_table_rows(value):
        if len(cells) < 5:
            continue
        entries.append(
            DdnsEntry(
                hostname=cells[0],
                username=cells[1],
                provider=cells[2],
                interface=cells[3],
                status=cells[4],
                remove_token=remove_token,
            )
        )
    return entries


def validate_ip(value: str, label: str) -> None:
    try:
        ipaddress.ip_address(value)
    except ValueError as error:
        raise RouterError(f"{label} não é um endereço IP válido: {value}") from error


def validate_port(value: str, label: str) -> None:
    try:
        port = int(value)
    except ValueError as error:
        raise RouterError(f"{label} não é uma porta válida: {value}") from error

    if port < 1 or port > 65535:
        raise RouterError(f"{label} deve estar entre 1 e 65535.")


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
        raise RouterError("Guardar credenciais encriptadas só é suportado no Windows.")

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
        raise RouterError("O Windows não conseguiu encriptar as credenciais.")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def windows_decrypt(data: bytes) -> bytes:
    if os.name != "nt":
        raise RouterError("Credenciais guardadas só são suportadas no Windows.")

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
        raise RouterError("O Windows não conseguiu desencriptar as credenciais guardadas.")

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
    input("\nPrima Enter para continuar...")


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
    print("\nCONFIRMAÇÃO DE SEGURANÇA")
    print("-" * 52)
    print(f"Modo atual:      {'BRIDGE' if current_bridge else 'ROUTER'}")
    print(f"Modo pedido:     {'BRIDGE' if desired_bridge else 'ROUTER'}")
    print()
    print("Alterar o modo bridge pode interromper a rede de casa.")
    if desired_bridge:
        print("Ao ativar o modo bridge, a porta LAN 4 será usada para bridge.")
    print("Continua apenas se tiveres a certeza.")
    print()
    return input("Escreve YES para continuar: ").strip() == "YES"


def connect_with_credentials(credentials: SavedCredentials) -> MeoRouter:
    router = MeoRouter(credentials.router_ip)
    print("\nA fazer login...")
    router.login(username=credentials.username, password=credentials.password)
    print("Login concluído.")
    return router


def ask_credentials(router_ip: str | None = None) -> SavedCredentials:
    router_ip = router_ip or ask(
        "IP do router - prima Enter para usar o valor predefinido, ou indique outro IP",
        DEFAULT_ROUTER,
    )
    username = ask("Utilizador")
    if not username:
        raise RouterError("O utilizador não pode ficar vazio.")

    password = getpass.getpass("Password do router: ")
    if not password:
        raise RouterError("A password não pode ficar vazia.")

    return SavedCredentials(router_ip=router_ip, username=username, password=password)


def maybe_save_credentials(credentials: SavedCredentials) -> None:
    answer = input("\nGuardar credenciais encriptadas para a próxima vez? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        return

    save_credentials(credentials)
    print("\nCredenciais encriptadas guardadas.")
    print(f"Ficheiro: {credentials_path()}")
    print("Estão protegidas pelo Windows para este utilizador neste PC.")


def connect_interactively(router_ip: str | None = None) -> MeoRouter:
    print_header()

    saved = None if router_ip else load_credentials()
    while saved:
        print("\nCredenciais guardadas encontradas")
        print("-" * 52)
        print(f"Ficheiro:  {credentials_path()}")
        print("Segurança: encriptadas pelo Windows para este utilizador neste PC")
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

        print("Selecione uma opção válida.")

    credentials = ask_credentials(router_ip)
    router = connect_with_credentials(credentials)
    maybe_save_credentials(credentials)
    return router


def interactive_menu(router: MeoRouter) -> int:
    while True:
        print("\nSelecione uma opção:")
        print("  1 - Ver estado")
        print("  2 - Wi-Fi")
        print("  3 - DNS")
        print("  4 - Modo bridge")
        print("  5 - Port forwarding")
        print("  6 - UPnP")
        print("  7 - DNS dinâmico")
        print("  8 - Credenciais guardadas")
        print("  0 - Sair")

        choice = input("\nOpção: ").strip()

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
                port_forward_menu(router)
            elif choice == "6":
                upnp_menu(router)
            elif choice == "7":
                ddns_menu(router)
            elif choice == "8":
                credentials_menu()
            elif choice == "0":
                print("Até breve.")
                return 0
            else:
                print("Selecione uma opção válida.")
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

        choice = input("\nOpção: ").strip()
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
            print("Selecione uma opção válida.")


def dns_menu(router: MeoRouter) -> None:
    while True:
        print("\nDNS")
        print("-" * 52)
        print("  1 - Ver DNS atual")
        print("  2 - Definir DNS manualmente")
        print("  3 - Cloudflare: 1.1.1.1 / 1.0.0.1")
        print("  4 - Google: 8.8.8.8 / 8.8.4.4")
        print("  5 - Quad9: 9.9.9.9 / 149.112.112.112")
        print("  6 - MEO: 212.55.154.190 / 212.55.154.174")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
        if choice == "1":
            current = router.get_lan_configuration()
            print(f"\nDNS atual: {current.get('dns') or 'automático'}")
            pause()
        elif choice == "2":
            change_dns(router)
            pause()
        elif choice == "3":
            change_dns(router, "1.1.1.1", "1.0.0.1")
            pause()
        elif choice == "4":
            change_dns(router, "8.8.8.8", "8.8.4.4")
            pause()
        elif choice == "5":
            change_dns(router, "9.9.9.9", "149.112.112.112")
            pause()
        elif choice == "6":
            change_dns(router, "212.55.154.190", "212.55.154.174")
            pause()
        elif choice == "0":
            return
        else:
            print("Selecione uma opção válida.")


def bridge_menu(router: MeoRouter) -> None:
    while True:
        print("\nModo bridge")
        print("-" * 52)
        print("  1 - Ver estado do bridge")
        print("  2 - Ativar modo bridge")
        print("  3 - Desativar modo bridge")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
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
            print("Selecione uma opção válida.")


def port_forward_menu(router: MeoRouter) -> None:
    while True:
        print("\nPort forwarding")
        print("-" * 52)
        print("  1 - Listar regras")
        print("  2 - Adicionar regra")
        print("  3 - Remover regra")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
        if choice == "1":
            list_port_forward_entries(router)
            pause()
        elif choice == "2":
            add_port_forward_interactive(router)
            pause()
        elif choice == "3":
            remove_port_forward_interactive(router)
            pause()
        elif choice == "0":
            return
        else:
            print("Selecione uma opção válida.")


def list_port_forward_entries(router: MeoRouter) -> list[PortForwardEntry]:
    entries = router.get_port_forward_entries()
    if not entries:
        print("\nNão existem regras de port forwarding.")
        return entries

    print("\nRegras de port forwarding")
    print("-" * 52)
    for index, entry in enumerate(entries, start=1):
        print(
            f"{index}. {entry.name} | {entry.protocol} | "
            f"{entry.external_start}-{entry.external_end} -> "
            f"{entry.server_ip}:{entry.internal_start}-{entry.internal_end}"
        )
    return entries


def add_port_forward_interactive(router: MeoRouter) -> None:
    print("\nNova regra de port forwarding")
    print("-" * 52)
    name = ask("Nome da regra")
    server_ip = ask("IP interno")
    external_start = ask("Porta externa inicial")
    external_end = ask("Porta externa final", external_start)
    internal_start = ask("Porta interna inicial", external_start)
    internal_end = ask("Porta interna final", internal_start)

    print("\nProtocolo")
    print("  1 - TCP")
    print("  2 - UDP")
    print("  3 - TCP/UDP")
    protocol_choice = ask("Opção", "3")
    if protocol_choice not in PROTOCOLS:
        raise RouterError("Protocolo inválido.")

    protocol_label_value, protocol_value = PROTOCOLS[protocol_choice]
    print()
    print(f"Nome:       {name}")
    print(f"Destino:    {server_ip}")
    print(f"Protocolo:  {protocol_label_value}")
    print(f"Externa:    {external_start}-{external_end}")
    print(f"Interna:    {internal_start}-{internal_end}")

    answer = input("Adicionar esta regra? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.add_port_forward(
        name=name,
        server_ip=server_ip,
        protocol=protocol_value,
        external_start=external_start,
        external_end=external_end,
        internal_start=internal_start,
        internal_end=internal_end,
    )
    print("Regra adicionada e validada.")


def remove_port_forward_interactive(router: MeoRouter) -> None:
    entries = list_port_forward_entries(router)
    if not entries:
        return

    selected = ask("Número da regra a remover")
    try:
        entry = entries[int(selected) - 1]
    except (ValueError, IndexError) as error:
        raise RouterError("Seleção inválida.") from error

    answer = input(f"Remover a regra '{entry.name}'? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.remove_port_forward(entry.remove_token)
    print("Regra removida.")


def upnp_menu(router: MeoRouter) -> None:
    while True:
        print("\nUPnP")
        print("-" * 52)
        print("  1 - Ver estado")
        print("  2 - Ativar UPnP")
        print("  3 - Desativar UPnP")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
        if choice == "1":
            print(f"\nUPnP: {'ON' if router.get_upnp_status() else 'OFF'}")
            pause()
        elif choice == "2":
            router.set_upnp_status(True)
            print("UPnP ativado e validado.")
            pause()
        elif choice == "3":
            router.set_upnp_status(False)
            print("UPnP desativado e validado.")
            pause()
        elif choice == "0":
            return
        else:
            print("Selecione uma opção válida.")


def ddns_menu(router: MeoRouter) -> None:
    while True:
        print("\nDNS dinâmico")
        print("-" * 52)
        print("  1 - Listar configurações")
        print("  2 - Adicionar DynDNS")
        print("  3 - Adicionar No-IP")
        print("  4 - Remover configuração")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
        if choice == "1":
            list_ddns_entries(router)
            pause()
        elif choice == "2":
            add_ddns_interactive(router, "1")
            pause()
        elif choice == "3":
            add_ddns_interactive(router, "2")
            pause()
        elif choice == "4":
            remove_ddns_interactive(router)
            pause()
        elif choice == "0":
            return
        else:
            print("Selecione uma opção válida.")


def list_ddns_entries(router: MeoRouter) -> list[DdnsEntry]:
    entries = router.get_ddns_entries()
    if not entries:
        print("\nNão existem configurações de DNS dinâmico.")
        return entries

    print("\nConfigurações de DNS dinâmico")
    print("-" * 52)
    for index, entry in enumerate(entries, start=1):
        print(f"{index}. {entry.provider} | {entry.hostname} | {entry.username} | {entry.interface}")
    return entries


def add_ddns_interactive(router: MeoRouter, provider: str) -> None:
    provider_label = "DynDNS" if provider == "1" else "No-IP"
    print(f"\nAdicionar {provider_label}")
    print("-" * 52)
    username = ask("Utilizador/email")
    password = getpass.getpass("Password DDNS: ")
    hostname = ask("Hostname")

    answer = input(f"Adicionar configuração {provider_label} para '{hostname}'? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.add_ddns(provider=provider, username=username, password=password, hostname=hostname)
    print("Configuração DDNS adicionada e validada.")


def remove_ddns_interactive(router: MeoRouter) -> None:
    entries = list_ddns_entries(router)
    if not entries:
        return

    selected = ask("Número da configuração a remover")
    try:
        entry = entries[int(selected) - 1]
    except (ValueError, IndexError) as error:
        raise RouterError("Seleção inválida.") from error

    answer = input(f"Remover DDNS '{entry.hostname}'? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.remove_ddns(entry.remove_token or entry.hostname)
    print("Configuração DDNS removida.")


def credentials_menu() -> None:
    while True:
        saved = load_credentials()
        print("\nCredenciais guardadas")
        print("-" * 52)
        if saved:
            print(f"Ficheiro:  {credentials_path()}")
            print("Segurança: encriptadas pelo Windows para este utilizador neste PC")
            print(f"IP router: {saved.router_ip}")
            print(f"Utilizador:{saved.username}")
        else:
            print("Não há credenciais guardadas.")
        print()
        print("  1 - Apagar credenciais guardadas")
        print("  0 - Voltar")

        choice = input("\nOpção: ").strip()
        if choice == "1":
            delete_saved_credentials()
            print("Credenciais guardadas apagadas.")
            pause()
        elif choice == "0":
            return
        else:
            print("Selecione uma opção válida.")


def change_wifi(router: MeoRouter, enabled: bool) -> None:
    current = router.get_wifi_status()
    print(f"\nWi-Fi atual: {'ON' if current else 'OFF'}")
    if current == enabled:
        print("Não é preciso alterar.")
        return

    router.set_wifi_status(enabled)
    print(f"O Wi-Fi está agora {'ON' if enabled else 'OFF'}.")


def change_dns(router: MeoRouter, primary: str | None = None, secondary: str | None = None) -> None:
    current = router.get_lan_configuration()
    print(f"\nDNS atual: {current.get('dns') or 'automático'}")

    primary = primary or ask("DNS primário", DEFAULT_PRIMARY_DNS)
    secondary = secondary if secondary is not None else ask("DNS secundário", DEFAULT_SECONDARY_DNS)

    print(f"\nNovo DNS: {primary}" + (f", {secondary}" if secondary else ""))
    answer = input("Aplicar esta configuração de DNS? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Cancelado.")
        return

    router.set_dns(primary_dns=primary, secondary_dns=secondary)
    print("Configuração de DNS atualizada e validada.")


def show_bridge_status(router: MeoRouter) -> None:
    bridge = router.get_bridge_status()
    print(f"\nModo: {'BRIDGE' if bridge else 'ROUTER'}")
    print(f"Valor routerMode do router: {router.get_router_mode_flag()}")


def change_bridge(router: MeoRouter, bridge_enabled: bool) -> None:
    current_bridge = router.get_bridge_status()
    if current_bridge == bridge_enabled:
        print(f"\nJá está em modo {'BRIDGE' if bridge_enabled else 'ROUTER'}.")
        return

    if not confirm_bridge_change(current_bridge, bridge_enabled):
        print("Cancelado.")
        return

    print("\nA alterar o modo do router...")
    router.set_bridge_status(bridge_enabled)
    print(f"O modo agora é {'BRIDGE' if bridge_enabled else 'ROUTER'}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ferramenta interativa para router MEO.",
        add_help=False,
    )
    parser._optionals.title = "opções"
    parser.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")
    parser.add_argument("--router", default=None, help=f"IP do router. Predefinição: {DEFAULT_ROUTER}")
    parser.add_argument(
        "--command",
        choices=["menu", "status", "wifi-on", "wifi-off", "dns", "bridge-status", "bridge-on", "bridge-off"],
        default="menu",
        help="Comando direto opcional. Por predefinição abre o menu.",
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
            input("\nPrima Enter para fechar...")


if __name__ == "__main__":
    raise SystemExit(main())
