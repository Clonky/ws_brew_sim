from fastapi import FastAPI
from uuid import uuid4
import uvicorn
from ws_brew_sim.simulation import Simulation
from ws_brew_sim.jobs import TransferJob, JobState

    
def create_app(simulation: Simulation):
    app = FastAPI()

    @app.post("/transfer_job")
    async def create_transfer_job(source_name: str, target_name: str, amount: int, rate: int):
        source = next((unit for unit in simulation.units if unit.name == source_name), None)
        target = next((unit for unit in simulation.units if unit.name == target_name), None)
        if source is None or target is None:
            return {"error": "Source or target unit not found"}
        job = TransferJob(name=source_name, job_id=str(uuid4()), state=JobState.PENDING, source=source, target=target, amount=amount, rate=rate)
        simulation.add_job(job)
        return {"message": f"Transfer job from {source_name} to {target_name} added."}

    @app.get("/")
    async def read_root():
        return {"message": "WS Brew Simulation API"}

    return app

async def create_interface(simulation: Simulation):
    app = create_app(simulation)
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()