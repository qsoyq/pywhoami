import asyncio
import logging
import socket

from collections import defaultdict
from enum import Enum
from itertools import cycle
from typing import List

import durationpy
import netifaces
import typer
import uvicorn

from fastapi import Body, FastAPI, Query, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse

from schema import ApiRes

cmd = typer.Typer()
app = FastAPI()

KB = 1 << 10
MB = 1 << 20
GB = 1 << 30
TB = 1 << 40
UNIT = {
    "kb": KB,
    "mb": MB,
    "gb": GB,
    "tb": TB,
}


class UnitEnum(str, Enum):
    kb = 'kb'
    mb = 'mb'
    gb = 'gb'
    tb = 'tb'


NAME = ""
HEALTH_STATUS_CODE = None
HEALTH_LOCK = asyncio.Lock()


@cmd.command()
def http(
    host: str = typer.Option("0.0.0.0",
                             '--host',
                             '-h',
                             envvar='http_host'),
    port: int = typer.Option(8000,
                             '--port',
                             '-p',
                             envvar='http_port'),
    debug: bool = typer.Option(False,
                               '--debug',
                               envvar='http_debug'),
    reload: bool = typer.Option(False,
                                '--debug',
                                envvar='http_reload'),
    log_level: int = typer.Option(logging.DEBUG,
                                  '--log_level',
                                  envvar='log_level'),
    name: str = typer.Option("",
                             '--name'),
    timeout_keep_alive: int = typer.Option(5,
                                           "--timeout_keep_alive",
                                           envvar="timeout_keep_alive")
):
    """启动 http 服务"""
    global NAME

    NAME = name
    logging.basicConfig(level=log_level)
    logging.info(f"http server listening on {host}:{port}")
    uvicorn.run("app:app", host=host, port=port, debug=debug, reload=reload, timeout_keep_alive=timeout_keep_alive)


def fillcontent(size: int):
    charset = '-ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    it = cycle(charset)
    if size == 0:
        return ''

    yield '|'
    for _ in range(size - 1):
        yield next(it)
    return '|'


def get_system_network_ip() -> List[str]:
    ip_list = []
    for i in netifaces.interfaces():
        addrs = netifaces.ifaddresses(i)

        for addr in addrs.get(netifaces.AF_INET6, []):
            ip_list.append(addr.get('addr'))

        for addr in addrs.get(netifaces.AF_INET, []):
            ip_list.append(addr.get('addr'))
    return ip_list


@app.get('/')
async def whoami(req: Request, wait: str = Query(None, description='接口阻塞时间, 如4h3m2s1ms')):
    resp = ''
    if wait:
        td = durationpy.from_str("wait")
        await asyncio.sleep(td.total_seconds())

    if NAME:
        resp = f"{resp}Name: {NAME}\n"

    hostname = socket.gethostname()
    resp = f'{resp}Hostname: {hostname}\n'
    for ip in get_system_network_ip():
        resp = f"{resp}IP: {ip}\n"

    remote_addr = f"{req.client.host}:{req.client.port}" if req.client else ''
    resp = f"{resp}RemoteAddr:{remote_addr}\n"
    for key, val in req.headers.items():
        resp = f'{resp}{key}: {val}\n'

    return Response(resp)


@app.get('/api', response_model=ApiRes)
async def api(req: Request):

    headers = defaultdict(list)
    for key, val in req.headers.items():
        headers[key].append(val)

    resp = {
        "remote_addr": f"{req.client.host}:{req.client.port}" if req.client else '',
        "hostname": socket.gethostname(),
        "ip": get_system_network_ip(),
        "headers": headers,
        "url": f"{req.url.path}?{req.url.query}" if req.url.query else req.url.path,
        "host": req.url.hostname,
        "method": req.method,
        "name": NAME,
    }

    return ApiRes(**resp)


@app.get('/health')
async def health():
    async with HEALTH_LOCK:
        statusCode = HEALTH_STATUS_CODE or 200
    return Response(status_code=statusCode)


@app.post('/health')
async def set_health(statusCode: int = Body(..., ge=100, lt=600, embed=True)):
    global HEALTH_STATUS_CODE

    logging.debug(f"Update health check status code [{statusCode}]\n")
    async with HEALTH_LOCK:
        HEALTH_STATUS_CODE = statusCode
    return


@app.get("/bench")
async def bench():
    return Response(content='1', headers={"Connection": "keep-alive", "Content-Type": "text/plain"})


@app.get("/data")
async def data(size: int = Query(..., gt=0), unit: UnitEnum = Query(...)):
    size *= UNIT[unit.value]
    return StreamingResponse(fillcontent(size))


@app.get('/echo')
async def echo():
    html = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Chat</title>
        </head>
        <body>
            <h1>WebSocket Chat</h1>
            <form action="" onsubmit="sendMessage(event)">
                <input type="text" id="messageText" autocomplete="off"/>
                <button>Send</button>
            </form>
            <ul id='messages'>
            </ul>
            <script>

                var ws = new WebSocket(window.location.href.replace("http", "ws"));
                // var ws = new WebSocket("ws://localhost:8000/ws");
                ws.onmessage = function(event) {
                    var messages = document.getElementById('messages')
                    var message = document.createElement('li')
                    var content = document.createTextNode(event.data)
                    message.appendChild(content)
                    messages.appendChild(message)
                };
                function sendMessage(event) {
                    var input = document.getElementById("messageText")
                    ws.send(input.value)
                    input.value = ''
                    event.preventDefault()
                }
            </script>
        </body>
    </html>
    """
    return HTMLResponse(html)


@app.websocket("/echo")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        print(f'received text:{data}')
        await websocket.send_text(f"Message text was: {data}")


if __name__ == '__main__':
    cmd()
