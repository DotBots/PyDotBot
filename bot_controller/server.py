"""Module for the web server application."""

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse


app = FastAPI(
    debug=1,
    title="DotBot controller API",
    description="This is the DotBot controller API",
    version="1.0.0",
    docs_url="/api",
    redoc_url=None,
)


@app.get(
    path="/dotbots",
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots():
    """Dotbots HTTP GET handler."""
    content = f"""
    <html>
        <head>
            <title>DotBots</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-Zenh87qX5JnK2Jl0vWa8Ck2rdkQ2Bzep5IDxbcnCeuOxjzrPF/et3URy9Bv1WTRi" crossorigin="anonymous">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg bg-dark">
                <div class="container-fluid">
                    <a class="navbar-brand text-light" href="#">DotBots</a>
                </div>
            </nav>
            <div class="container">
                <div class="card m-1">
                    <div class="card-header">
                        Available DotBots
                    </div>
                    <div class="card-body p-0">
                        <table class="table table-dark table-striped">
                            <thead>
                                <tr>
                                  <th>Address</th>
                                  <th>Last seen</th>
                                  <th>Active</th>
                                </tr>
                            </thead>
                            <tbody>
                                {"".join(
                                    "<tr>"
                                    f"    <td>0x{dotbot.address}</td>"
                                    f"    <td>{dotbot.last_seen}</td>"
                                    f"    <td>{dotbot.active}</td>"
                                    f"</tr>"
                                    for dotbot in app.controller.dotbots.values()
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=content)


@app.put(
    path="/dotbots/{address}",
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots_current(address):
    """Set the current active DotBot."""
    app.controller.header.dotbot_address = int(address, 16)
    for dotbot in app.controller.dotbots.values():
        dotbot.active = False
    if address in app.controller.dotbots:
        app.controller.dotbots[address].active = True


async def web(controller):
    """Starts the web server application."""
    app.controller = controller
    config = uvicorn.Config(app, port=8000, log_level="debug")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except asyncio.exceptions.CancelledError:
        print("Web server cancelled")
    else:
        raise SystemExit()
