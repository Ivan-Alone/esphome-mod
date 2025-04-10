from __future__ import annotations

import gzip
import base64
import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import web_server_base
from esphome.components.web_server_base import CONF_WEB_SERVER_BASE_ID
from esphome.const import (
    CONF_CSS_INCLUDE,
    CONF_CSS_URL,
    CONF_ID,
    CONF_JS_INCLUDE,
    CONF_JS_URL,
    CONF_ADD_HEAD,
    CONF_ADD_BODY,
    CONF_ADD_FAVICON,
    CONF_ADD_APPLE_ICON,
    CONF_ADD_MANIFEST,
    CONF_LANG,
    CONF_HEADER_CACHE_CONTROL,
    CONF_ENABLE_PRIVATE_NETWORK_ACCESS,
    CONF_PORT,
    CONF_AUTH,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_INCLUDE_INTERNAL,
    CONF_OTA,
    CONF_LOG,
    CONF_VERSION,
    CONF_LOCAL,
    CONF_WEB_SERVER_ID,
    CONF_WEB_SERVER_SORTING_WEIGHT,
    PLATFORM_ESP32,
    PLATFORM_ESP8266,
    PLATFORM_BK72XX,
    PLATFORM_RTL87XX,
)
from esphome.core import CORE, coroutine_with_priority

AUTO_LOAD = ["json", "web_server_base"]

web_server_ns = cg.esphome_ns.namespace("web_server")
WebServer = web_server_ns.class_("WebServer", cg.Component, cg.Controller)


def default_url(config):
    config = config.copy()
    if config[CONF_VERSION] == 1:
        if CONF_CSS_URL not in config:
            config[CONF_CSS_URL] = "https://esphome.io/_static/webserver-v1.min.css"
        if CONF_JS_URL not in config:
            config[CONF_JS_URL] = "https://esphome.io/_static/webserver-v1.min.js"
    if config[CONF_VERSION] == 2:
        if CONF_CSS_URL not in config:
            config[CONF_CSS_URL] = ""
        if CONF_JS_URL not in config:
            config[CONF_JS_URL] = "https://oi.esphome.io/v2/www.js"
    if config[CONF_VERSION] == 3:
        if CONF_CSS_URL not in config:
            config[CONF_CSS_URL] = ""
        if CONF_JS_URL not in config:
            config[CONF_JS_URL] = "https://oi.esphome.io/v3/www.js"
    return config


def validate_local(config):
    if CONF_LOCAL in config and config[CONF_VERSION] == 1:
        raise cv.Invalid("'local' is not supported in version 1")
    return config


def validate_ota(config):
    if CORE.using_esp_idf and config[CONF_OTA]:
        raise cv.Invalid("Enabling 'ota' is not supported for IDF framework yet")
    return config


def _validate_no_sorting_weight(
    webserver_version: int, config: dict, path: list[str] | None = None
) -> None:
    if path is None:
        path = []
    if CONF_WEB_SERVER_SORTING_WEIGHT in config:
        raise cv.FinalExternalInvalid(
            f"Sorting weight on entities is not supported in web_server version {webserver_version}",
            path=path + [CONF_WEB_SERVER_SORTING_WEIGHT],
        )
    for p, value in config.items():
        if isinstance(value, dict):
            _validate_no_sorting_weight(webserver_version, value, path + [p])
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _validate_no_sorting_weight(webserver_version, item, path + [p, i])


def _final_validate_sorting_weight(config):
    if (webserver_version := config.get(CONF_VERSION)) != 3:
        _validate_no_sorting_weight(webserver_version, fv.full_config.get())

    return config


FINAL_VALIDATE_SCHEMA = _final_validate_sorting_weight


WEBSERVER_SORTING_SCHEMA = cv.Schema(
    {
        cv.OnlyWith(CONF_WEB_SERVER_ID, "web_server"): cv.use_id(WebServer),
        cv.Optional(CONF_WEB_SERVER_SORTING_WEIGHT): cv.All(
            cv.requires_component("web_server"),
            cv.float_,
        ),
    }
)


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(WebServer),
            cv.Optional(CONF_PORT, default=80): cv.port,
            cv.Optional(CONF_VERSION, default=2): cv.one_of(1, 2, 3, int=True),
            cv.Optional(CONF_CSS_URL): cv.string,
            cv.Optional(CONF_CSS_INCLUDE): cv.file_,
            cv.Optional(CONF_JS_URL): cv.string,
            cv.Optional(CONF_ADD_BODY): cv.string,
            cv.Optional(CONF_ADD_HEAD): cv.string,
            cv.Optional(CONF_ADD_APPLE_ICON): cv.string,
            cv.Optional(CONF_ADD_FAVICON): cv.string,
            cv.Optional(CONF_ADD_MANIFEST): cv.string,
            cv.Optional(CONF_LANG): cv.string,
            cv.Optional(CONF_HEADER_CACHE_CONTROL): cv.string,
            cv.Optional(CONF_JS_INCLUDE): cv.file_,
            cv.Optional(CONF_ENABLE_PRIVATE_NETWORK_ACCESS, default=True): cv.boolean,
            cv.Optional(CONF_AUTH): cv.Schema(
                {
                    cv.Required(CONF_USERNAME): cv.All(
                        cv.string_strict, cv.Length(min=1)
                    ),
                    cv.Required(CONF_PASSWORD): cv.All(
                        cv.string_strict, cv.Length(min=1)
                    ),
                }
            ),
            cv.GenerateID(CONF_WEB_SERVER_BASE_ID): cv.use_id(
                web_server_base.WebServerBase
            ),
            cv.Optional(CONF_INCLUDE_INTERNAL, default=False): cv.boolean,
            cv.SplitDefault(
                CONF_OTA,
                esp8266=True,
                esp32_arduino=True,
                esp32_idf=False,
                bk72xx=True,
                rtl87xx=True,
            ): cv.boolean,
            cv.Optional(CONF_LOG, default=True): cv.boolean,
            cv.Optional(CONF_LOCAL): cv.boolean,
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on([PLATFORM_ESP32, PLATFORM_ESP8266, PLATFORM_BK72XX, PLATFORM_RTL87XX]),
    default_url,
    validate_local,
    validate_ota,
)


def add_entity_to_sorting_list(web_server, entity, config):
    sorting_weight = 50
    if CONF_WEB_SERVER_SORTING_WEIGHT in config:
        sorting_weight = config[CONF_WEB_SERVER_SORTING_WEIGHT]

    cg.add(
        web_server.add_entity_to_sorting_list(
            entity,
            sorting_weight,
        )
    )


def build_index_html(config) -> str:
    html = "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"/>"
    
    head = config.get(CONF_ADD_HEAD)
    if head:
        html += head
    
    favicon = config.get(CONF_ADD_FAVICON)
    if favicon:
        html += "<link rel=\"icon\" href=\"/favicon.png\" />"
    else:
        html += "<link rel=icon href=data:>"
    
    apple_icon = config.get(CONF_ADD_APPLE_ICON)
    if apple_icon:
        html += "<link rel=\"apple-touch-icon\" href=\"/apple_icon.png\" />"
        html += "<link rel=\"apple-touch-startup-image\" href=\"/apple_icon.png\" />"
        
    manifest = config.get(CONF_ADD_MANIFEST)
    if manifest:
        html += "<link rel=\"manifest\" crossorigin=\"use-credentials\" href=\"/manifest.webmanifest\"/>"
    
    css_include = config.get(CONF_CSS_INCLUDE)
    js_include = config.get(CONF_JS_INCLUDE)
    if css_include:
        html += "<link rel=stylesheet href=/0.css>"
    if config[CONF_CSS_URL]:
        html += f'<link rel=stylesheet href="{config[CONF_CSS_URL]}">'
    html += "</head><body>"
    
    html_extra = config.get(CONF_ADD_BODY)
    if html_extra:
        html += html_extra
    
    if js_include:
        html += "<script type=module src=/0.js></script>"
    html += "<esp-app></esp-app>"
    if config[CONF_JS_URL]:
        html += f'<script src="{config[CONF_JS_URL]}"></script>'
    html += "</body></html>"
    return html


def add_resource_as_progmem(
    resource_name: str, content: str, compress: bool = True
) -> None:
    """Add a resource to progmem."""
    try:
        content_encoded = content.encode("utf-8")
    except AttributeError:
        content_encoded = content
    if compress:
        content_encoded = gzip.compress(content_encoded)
    content_encoded_size = len(content_encoded)
    bytes_as_int = ", ".join(str(x) for x in content_encoded)
    uint8_t = f"const uint8_t ESPHOME_WEBSERVER_{resource_name}[{content_encoded_size}] PROGMEM = {{{bytes_as_int}}}"
    size_t = (
        f"const size_t ESPHOME_WEBSERVER_{resource_name}_SIZE = {content_encoded_size}"
    )
    cg.add_global(cg.RawExpression(uint8_t))
    cg.add_global(cg.RawExpression(size_t))


@coroutine_with_priority(40.0)
async def to_code(config):
    paren = await cg.get_variable(config[CONF_WEB_SERVER_BASE_ID])

    var = cg.new_Pvariable(config[CONF_ID], paren)
    await cg.register_component(var, config)

    cg.add_define("USE_WEBSERVER")
    version = config[CONF_VERSION]

    cg.add(paren.set_port(config[CONF_PORT]))
    cg.add_define("USE_WEBSERVER")
    cg.add_define("USE_WEBSERVER_PORT", config[CONF_PORT])
    cg.add_define("USE_WEBSERVER_VERSION", version)
    if version >= 2:
        # Don't compress the index HTML as the data sizes are almost the same.
        add_resource_as_progmem("INDEX_HTML", build_index_html(config), compress=False)
    else:
        cg.add(var.set_css_url(config[CONF_CSS_URL]))
        cg.add(var.set_js_url(config[CONF_JS_URL]))
    cg.add(var.set_allow_ota(config[CONF_OTA]))
    cg.add(var.set_expose_log(config[CONF_LOG]))
    if CONF_LANG in config:
        cg.add(var.set_lang(config[CONF_LANG]))
    if config[CONF_ENABLE_PRIVATE_NETWORK_ACCESS]:
        cg.add_define("USE_WEBSERVER_PRIVATE_NETWORK_ACCESS")
    if CONF_AUTH in config:
        cg.add(paren.set_auth_username(config[CONF_AUTH][CONF_USERNAME]))
        cg.add(paren.set_auth_password(config[CONF_AUTH][CONF_PASSWORD]))
    if CONF_CSS_INCLUDE in config:
        cg.add_define("USE_WEBSERVER_CSS_INCLUDE")
        path = CORE.relative_config_path(config[CONF_CSS_INCLUDE])
        with open(file=path, encoding="utf-8") as css_file:
            add_resource_as_progmem("CSS_INCLUDE", css_file.read())
    if CONF_JS_INCLUDE in config:
        cg.add_define("USE_WEBSERVER_JS_INCLUDE")
        path = CORE.relative_config_path(config[CONF_JS_INCLUDE])
        with open(file=path, encoding="utf-8") as js_file:
            add_resource_as_progmem("JS_INCLUDE", js_file.read())
    if CONF_ADD_MANIFEST in config:
        cg.add_define("USE_WEBSERVER_MANIFEST_INCLUDE")
        path = CORE.relative_config_path(config[CONF_ADD_MANIFEST])
        with open(file=path, encoding="utf-8") as manifest_file:
            add_resource_as_progmem("MANIFEST_INCLUDE", manifest_file.read())
    if CONF_ADD_FAVICON in config:
        cg.add_define("USE_WEBSERVER_FAVICON_INCLUDE")
        path = CORE.relative_config_path(config[CONF_ADD_FAVICON])
        with open(file=path, mode="rb") as icon_file:
            add_resource_as_progmem("FAVICON_INCLUDE", icon_file.read())
    if CONF_ADD_APPLE_ICON in config:
        cg.add_define("USE_WEBSERVER_APPLE_ICON_INCLUDE")
        path = CORE.relative_config_path(config[CONF_ADD_APPLE_ICON])
        with open(file=path, mode="rb") as icon_file:
            add_resource_as_progmem("APPLE_ICON_INCLUDE", icon_file.read())
    cg.add(var.set_include_internal(config[CONF_INCLUDE_INTERNAL]))
    if CONF_LOCAL in config and config[CONF_LOCAL]:
        cg.add_define("USE_WEBSERVER_LOCAL")
    if CONF_HEADER_CACHE_CONTROL in config:
        cg.add_define("USE_WEBSERVER_CACHE_CONTROL", config[CONF_HEADER_CACHE_CONTROL])
