import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_BASE_URL = "https://api.pexels.com"

try:
    mcp = FastMCP("Pexels MCP", stateless_http=True, json_response=True)
except TypeError:
    mcp = FastMCP("Pexels MCP")


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


@mcp.tool()
async def buscar_fotos(query: str, per_page: int = 10) -> str:
    """Busca fotos de alta qualidade no Pexels."""
    data = await _pexels_get(
        "/v1/search",
        {"query": query, "per_page": _limit_per_page(per_page, 10, 80)},
    )
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
async def buscar_videos(query: str, per_page: int = 5) -> str:
    """Busca vídeos de B-roll gratuitos no Pexels."""
    data = await _pexels_get(
        "/videos/search",
        {"query": query, "per_page": _limit_per_page(per_page, 5, 80)},
    )
    return json.dumps(data, ensure_ascii=False)


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
              <p>Servidor MCP com tools <code>buscar_fotos</code> e <code>buscar_videos</code>.</p>
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


if hasattr(mcp, "streamable_http_app"):
    mcp_asgi_app = mcp.streamable_http_app()
elif hasattr(mcp, "app"):
    mcp_asgi_app = mcp.app
else:
    raise RuntimeError("Esta versão do pacote mcp não expõe app ASGI/HTTP compatível.")

app = Starlette(
    routes=[
        Route("/", endpoint=home, methods=["GET"]),
        Route("/fotos", endpoint=fotos_http, methods=["GET"]),
        Route("/videos", endpoint=videos_http, methods=["GET"]),
        Mount("/", app=mcp_asgi_app),
    ]
)
