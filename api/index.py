import json
import os
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_BASE_URL = "https://api.pexels.com"
MCP_PROTOCOL_VERSION = "2024-11-05"


def _limit_per_page(value: Any, default: int, max_value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, max_value))


async def _pexels_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if not PEXELS_API_KEY:
        return {
            "error": "PEXELS_API_KEY não configurada.",
            "how_to_fix": "Adicione PEXELS_API_KEY nas Environment Variables do projeto na Vercel.",
        }

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            f"{PEXELS_BASE_URL}{path}",
            params=params,
            headers={"Authorization": PEXELS_API_KEY},
        )

    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if response.status_code >= 400:
        return {
            "error": "A API do Pexels retornou erro.",
            "status_code": response.status_code,
            "details": payload,
        }

    return payload


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _json_rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        status_code=200,
    )


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "buscar_fotos",
            "description": "Busca fotos de alta qualidade no Pexels.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca, por exemplo: natureza, carneiros, agricultura.",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Quantidade de resultados. Padrão: 10.",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 80,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "buscar_videos",
            "description": "Busca vídeos de B-roll gratuitos no Pexels.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca, por exemplo: cidade, campo, produtos.",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Quantidade de resultados. Padrão: 5.",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 80,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    ]


async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"error": "O parâmetro query é obrigatório."}, ensure_ascii=False),
                }
            ],
            "isError": True,
        }

    if name == "buscar_fotos":
        per_page = _limit_per_page(arguments.get("per_page", 10), 10, 80)
        data = await _pexels_get("/v1/search", {"query": query, "per_page": per_page})
    elif name == "buscar_videos":
        per_page = _limit_per_page(arguments.get("per_page", 5), 5, 80)
        data = await _pexels_get("/videos/search", {"query": query, "per_page": per_page})
    else:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"error": f"Tool desconhecida: {name}"}, ensure_ascii=False),
                }
            ],
            "isError": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False),
            }
        ]
    }


async def mcp_http(request: Request) -> Response:
    if request.method == "GET":
        return JSONResponse(
            {
                "name": "Pexels MCP",
                "status": "ok",
                "protocol": "MCP over HTTP JSON-RPC",
                "tools": [tool["name"] for tool in _tool_definitions()],
            }
        )

    try:
        payload = await request.json()
    except Exception:
        return _json_rpc_error(None, -32700, "JSON inválido.")

    # Alguns clientes podem enviar batch JSON-RPC.
    if isinstance(payload, list):
        responses = []
        for item in payload:
            response = await _handle_mcp_message(item)
            if response is not None:
                responses.append(response)
        return JSONResponse(responses)

    response = await _handle_mcp_message(payload)
    if response is None:
        # JSON-RPC notification sem id.
        return Response(status_code=202)
    return JSONResponse(response)


async def _handle_mcp_message(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if request_id is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", MCP_PROTOCOL_VERSION),
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Pexels MCP",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": _tool_definitions()},
        }

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        result = await _call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Método não encontrado: {method}"},
    }


async def home(_: Request) -> HTMLResponse:
    configured = "configurada" if bool(PEXELS_API_KEY) else "não configurada"
    return HTMLResponse(
        f"""
        <!doctype html>
        <html lang="pt-BR">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Pexels MCP</title>
            <style>
              body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #050816; color: #f8fafc; font-family: system-ui, sans-serif; }}
              main {{ width: min(860px, calc(100vw - 32px)); padding: 40px; border: 1px solid #334155; border-radius: 24px; background: #0f172a; }}
              h1 {{ font-size: clamp(2rem, 5vw, 4rem); margin: 0 0 16px; }}
              p {{ color: #cbd5e1; font-size: 1.05rem; }}
              pre {{ overflow: auto; padding: 16px; border-radius: 12px; background: #020617; border: 1px solid #334155; }}
              code {{ background: #1e293b; padding: 2px 6px; border-radius: 8px; }}
            </style>
          </head>
          <body>
            <main>
              <p><code>PEXELS_API_KEY</code>: {configured}</p>
              <h1>Pexels MCP</h1>
              <p>Servidor MCP HTTP com tools <code>buscar_fotos</code> e <code>buscar_videos</code>.</p>
              <pre>/mcp\n/fotos?query=natureza&per_page=5\n/videos?query=cidade&per_page=3</pre>
            </main>
          </body>
        </html>
        """
    )


async def fotos_http(request: Request) -> JSONResponse:
    query = request.query_params.get("query", "natureza")
    per_page = _limit_per_page(request.query_params.get("per_page", 10), 10, 80)
    data = await _pexels_get("/v1/search", {"query": query, "per_page": per_page})
    return JSONResponse(data)


async def videos_http(request: Request) -> JSONResponse:
    query = request.query_params.get("query", "natureza")
    per_page = _limit_per_page(request.query_params.get("per_page", 5), 5, 80)
    data = await _pexels_get("/videos/search", {"query": query, "per_page": per_page})
    return JSONResponse(data)


app = Starlette(
    routes=[
        Route("/", endpoint=home, methods=["GET"]),
        Route("/fotos", endpoint=fotos_http, methods=["GET"]),
        Route("/videos", endpoint=videos_http, methods=["GET"]),
        Route("/mcp", endpoint=mcp_http, methods=["GET", "POST"]),
        Route("/mcp/", endpoint=mcp_http, methods=["GET", "POST"]),
    ]
)
