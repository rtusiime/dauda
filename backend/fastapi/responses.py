class Response:
    def __init__(self, content: str, media_type: str = "application/octet-stream") -> None:
        self.body = content
        self.media_type = media_type


class PlainTextResponse(Response):
    media_type = "text/plain"


class HTMLResponse(Response):
    media_type = "text/html"


class JSONResponse(Response):
    media_type = "application/json"


class FileResponse(Response):
    media_type = "application/octet-stream"


__all__ = ["Response", "PlainTextResponse", "HTMLResponse", "JSONResponse", "FileResponse"]
