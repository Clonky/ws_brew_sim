from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
from typing import Annotated
import uvicorn
from ws_brew_sim.units import Unit
from ws_brew_sim.simulation import Simulation
from ws_brew_sim.jobs import TransferJob, JobState, FilterJob
from asyncua import ua

    
def create_app(simulation: Simulation):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="static"), name="static")

    templates = Jinja2Templates(directory="templates")

    @app.post("/transfer_job")
    async def create_transfer_job(source_name: Annotated[str, Form()], target_name: Annotated[str, Form()], amount: Annotated[int, Form()], rate: Annotated[int, Form()]):
        source = next((unit for unit in simulation.units if unit.name == source_name), None)
        target = next((unit for unit in simulation.units if unit.name == target_name), None)
        if source is None or target is None:
            return {"error": "Source or target unit not found"}
        job = TransferJob(name=source_name, job_id=str(uuid4()), state=JobState.PENDING, source=source, target=target, amount=amount, rate=rate)
        source.add_job(job)
        return {"message": f"Transfer job from {source_name} to {target_name} added."}
    
    @app.post("/filter_job")
    async def create_procedure_job(unit_name: Annotated[str, Form()], batch_id: Annotated[str, Form()], amount: Annotated[int, Form()]):
        unit = next((unit for unit in simulation.units if unit.name == unit_name), None)
        if unit is None:
            return {"error": "Unit not found"}
        job = FilterJob(
            name=unit,
            job_id=str(uuid4()),
            state=JobState.PENDING,
            batch_id=batch_id,
            filter_rate=10,
            amount_filtered=0,
            amount_to_filter=amount,
            )
        unit.add_job(job)
        return {"message": f"Filter job for unit {unit} added."}

    @app.get("/", response_class=HTMLResponse)
    async def read_root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/landing", response_class=HTMLResponse)
    async def landing(request: Request):
        return templates.TemplateResponse("landing.html", {"request": request})

    @app.get("/units", response_class=HTMLResponse)
    async def index_units(request: Request):
        return templates.TemplateResponse("units.html", {"request": request, "units": simulation.units})

    @app.post("/unit/{unit_name}/state/", response_class=HTMLResponse)
    async def change_state(request: Request, unit_name: str, state_name: str, action: str):
        unit = next((unit for unit in simulation.units if unit.name == unit_name), None)
        if unit:
            unit.statemachine.disable_all_states()
            state_path = unit.statemachine.get_path_to_state(state_name)
            for state in state_path:
                await state.curr_state_node.set_writable(True)
                if action == "deactivate":
                    await state.curr_state_node.write_value(ua.LocalizedText("Null", "en"))
                    state.active = False
                elif action == "activate":
                    await state.curr_state_node.write_value(ua.LocalizedText(state.name, "en"))
                    state.active = True
        return templates.TemplateResponse("show_unit.html", {"request": request, "unit": unit})


    @app.get("/value/{unit_name}/{module_name}", response_class=HTMLResponse)
    async def get_updated_value(request: Request, unit_name: str, module_name: str):
        unit: Unit | None = next((unit for unit in simulation.units if unit.name == unit_name), None)
        if unit is None:
            return HTMLResponse(content=f"<h2>Unit {unit_name} not found</h2>", status_code=404)
        module = next((mod for mod in unit.modules if mod.name == module_name), None)
        if module is None:
            return HTMLResponse(content=f"<h2>Module {module_name} not found in unit {unit_name}</h2>", status_code=404)
        value = module.update_behaviour.state if module.update_behaviour else "N/A"
        value = f"{value:.2f}" if isinstance(value, float) else str(value)
        return templates.TemplateResponse("module_value.html", {"request": request, "val": value})

    @app.get("/show_unit/{unit_name}", response_class=HTMLResponse)
    async def show_unit(request: Request, unit_name: str):
        unit: Unit | None = next((unit for unit in simulation.units if unit.name == unit_name), None)
        if unit is None:
            return HTMLResponse(content=f"<h2>Unit {unit_name} not found</h2>", status_code=404)
        return templates.TemplateResponse("show_unit.html", {"request": request, "unit": unit})

    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs(request: Request):
        units = simulation.units
        return templates.TemplateResponse("_jobs.html", {"request": request, "units": units})

    return app

async def create_interface(simulation: Simulation):
    app = create_app(simulation)
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()