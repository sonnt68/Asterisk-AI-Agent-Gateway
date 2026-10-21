"""Strict, secret-safe schemas for PBX administration APIs."""

import ipaddress
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
SAFE_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
NUMBER_PATTERN = r"^\+?[0-9]{1,32}$"


def _text(value: object, name: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError(f"{name} contains an invalid control character")
    if required and not value:
        raise ValueError(f"{name} is required")
    if len(value) > maximum:
        raise ValueError(f"{name} is too long")
    return value


def _host(value: object) -> str:
    value = _text(value, "host", 253, required=True)
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if not SAFE_HOSTNAME.fullmatch(value) or ".." in value:
            raise ValueError("host must be an IP address or hostname") from None
        return value


def _transport(value: object) -> str:
    value = _text(value, "transport", 64, required=True)
    if not SAFE_TOKEN.fullmatch(value):
        raise ValueError("transport must be an existing PBX transport name")
    return value


def _match(value: object) -> str:
    value = _text(value, "match", 2000)
    if not value:
        return value
    for item in value.split(","):
        item = item.strip()
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise ValueError("match must be a comma-separated IP/CIDR list") from None
    return value


def _codec(value: object) -> str:
    value = _text(value, "codec", 32, required=True)
    if not SAFE_TOKEN.fullmatch(value):
        raise ValueError("codec contains unsupported characters")
    return value


def _password(value: object) -> SecretStr | None:
    if value is None:
        return None
    secret = value.get_secret_value() if isinstance(value, SecretStr) else value
    _text(secret, "password", 256)
    return SecretStr(secret)


def _outbound_app_ids(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("outbound_partner_app_ids must be a list of at most 64 app IDs")
    result = [_text(item, "outbound_partner_app_id", 36, required=True) for item in value]
    if len(result) != len(set(result)):
        raise ValueError("outbound_partner_app_ids must be unique")
    return result


class TrunkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=5060, ge=1, le=65535)
    transport: str = "0.0.0.0-udp"
    authentication: Literal["none", "outbound"] = "none"
    registration: Literal["none", "send"] = "none"
    username: str = Field(default="", max_length=120)
    auth_username: str = Field(default="", max_length=120)
    password: SecretStr | None = None
    match: str = Field(default="", max_length=2000)
    from_domain: str = Field(default="", max_length=253)
    from_user: str = Field(default="", max_length=120)
    contact_user: str = Field(default="", max_length=120)
    outbound_caller_id: str = Field(default="", max_length=120)
    codecs: list[str] = Field(default_factory=list, max_length=32)
    enabled: bool = True

    _validate_host = field_validator("host")(_host)
    _validate_transport = field_validator("transport")(_transport)
    _validate_match = field_validator("match")(_match)
    _validate_password = field_validator("password", mode="before")(_password)
    _validate_codecs = field_validator("codecs")(lambda value: [_codec(item) for item in value])
    _validate_text = field_validator(
        "name", "username", "auth_username", "from_domain", "from_user",
        "contact_user", "outbound_caller_id",
    )(lambda value, info: _text(value, info.field_name, 253 if info.field_name == "from_domain" else 120))


class TrunkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    transport: str | None = None
    authentication: Literal["none", "outbound"] | None = None
    registration: Literal["none", "send"] | None = None
    username: str | None = Field(default=None, max_length=120)
    auth_username: str | None = Field(default=None, max_length=120)
    password: SecretStr | None = None
    match: str | None = Field(default=None, max_length=2000)
    from_domain: str | None = Field(default=None, max_length=253)
    from_user: str | None = Field(default=None, max_length=120)
    contact_user: str | None = Field(default=None, max_length=120)
    outbound_caller_id: str | None = Field(default=None, max_length=120)
    codecs: list[str] | None = Field(default=None, max_length=32)
    enabled: bool | None = None

    _validate_host = field_validator("host")(_host)
    _validate_transport = field_validator("transport")(_transport)
    _validate_match = field_validator("match")(_match)
    _validate_password = field_validator("password", mode="before")(_password)
    _validate_codecs = field_validator("codecs")(lambda value: [_codec(item) for item in value])
    _validate_text = field_validator(
        "name", "username", "auth_username", "from_domain", "from_user",
        "contact_user", "outbound_caller_id",
    )(lambda value, info: _text(value, info.field_name, 253 if info.field_name == "from_domain" else 120))


class PhoneNumberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: Annotated[str, Field(pattern=NUMBER_PATTERN, max_length=33)]
    label: str = Field(min_length=1, max_length=120)
    partner_app_id: str = Field(min_length=1, max_length=36)
    enabled: bool = True
    outbound_partner_app_ids: list[str] = Field(default_factory=list, max_length=64)

    _validate_label = field_validator("label")(
        lambda value: _text(value, "label", 120, required=True)
    )
    _validate_app = field_validator("partner_app_id")(
        lambda value: _text(value, "partner_app_id", 36, required=True)
    )
    _validate_outbound_apps = field_validator("outbound_partner_app_ids")(_outbound_app_ids)


class PhoneNumberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=120)
    partner_app_id: str | None = Field(default=None, min_length=1, max_length=36)
    enabled: bool | None = None
    outbound_partner_app_ids: list[str] | None = Field(default=None, max_length=64)

    _validate_label = field_validator("label")(
        lambda value: _text(value, "label", 120, required=True)
    )
    _validate_app = field_validator("partner_app_id")(
        lambda value: _text(value, "partner_app_id", 36, required=True)
    )
    _validate_outbound_apps = field_validator(
        "outbound_partner_app_ids"
    )(_outbound_app_ids)
