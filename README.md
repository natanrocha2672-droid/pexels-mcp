# Pexels MCP na Vercel

Servidor MCP em Python para buscar fotos e vídeos gratuitos no Pexels.

## Variável obrigatória

Configure na Vercel:

```env
PEXELS_API_KEY=sua_chave_do_pexels
```

## Endpoints

- `/` página de status
- `/fotos?query=natureza&per_page=5`
- `/videos?query=cidade&per_page=3`
- `/mcp` servidor MCP

## Tools MCP

- `buscar_fotos(query: str, per_page: int = 10)`
- `buscar_videos(query: str, per_page: int = 5)`
