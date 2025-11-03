# WS Brew Simulator

This library contains definitions of units and modules used for simulating a production environment in a brewery.
Currently implemented:

+ BrightBeerTank
+ FermentationTank
+ SheetFilter

The library is structured so that a list of units can be found in ```src/units.py```. A list of modules can be found in ```src/modules.py```.
The folder ```examples``` on the top level includes runnable example configurations of i.e. a filtration line.
These examples generally start an OPC UA server using the library ```asyncua```. The server can be browsed and subscribed to with a regular
OPC UA client like *UA Expert* or *SiOME*. Function has been tested with both. We were unable to get datachange subscriptions working in
combination of asyncua and *SiOME*.

In the background, a simulation is running that rudimentary implements transfers from one container to another. This will result in
**WSTransferEvents** being fired by the source container on completion. The simulation also supports filtration processes, which results in
respective **WSUnitProcedureEvents** being fired. These events can be subscribed to in the EventViewer of UAExpert.

You can interact with the server and monitor the activities of the units using an http interface on <http://127.0.0.1:8080> .
The web server starts up automatically when starting one of the examples. The web interface has the capability to create
jobs for the individual units and monitor values from their equipment modules.

## Requirements

+ Python3 >= 13.0
+ asyncua
+ fastapi
+ asyncio
+ jinja2
+ uvicorn
+ python-multipart
+ logger

Check requirements.txt or pyproject.toml for a detailed list of requirements
