"""sdnctl — intent + device control CLI."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import yaml
from rich import print as rprint
from rich.syntax import Syntax
from rich.table import Table

from ..drivers import driver_for
from ..models.intent import IntentDocument
from ..models.inventory import Device, DeviceCredential, Vendor
from ..reconciler import reconcile_once
from ..reconciler.loop import push_device
from ..render import config_diff, render_device
from ..store import DeviceRepo, IntentRepo, get_session, init_db

app = typer.Typer(add_completion=False, help="Campus EVPN SDN controller CLI.")


def _load_intent(path: Path) -> IntentDocument:
    data = yaml.safe_load(path.read_text())
    return IntentDocument.model_validate(data)


@app.command("apply-intent")
def apply_intent(
    intent_path: Path = typer.Option(..., "--intent", "-f", exists=True, readable=True),
) -> None:
    """Persist an intent YAML file to the controller store."""
    doc = _load_intent(intent_path)

    async def _go() -> None:
        await init_db()
        async for session in get_session():
            await IntentRepo(session).save(doc)
    asyncio.run(_go())
    rprint(f"[green]intent applied:[/green] fabric={doc.fabric.name}, nodes={len(doc.fabric.nodes)}, tenants={len(doc.tenants)}")


@app.command("add-device")
def add_device(
    name: str = typer.Option(...),
    vendor: Vendor = typer.Option(...),
    mgmt: str = typer.Option(..., help="Management IP (v4 or v6)"),
    username: str = typer.Option("sdn"),
    password: str | None = typer.Option(None, help="Optional password (otherwise key auth)"),
    ssh_key: str | None = typer.Option(None),
    os_version: str | None = typer.Option(None),
) -> None:
    """Register a device in the inventory."""
    dev = Device(
        name=name,
        vendor=vendor,
        mgmt_address=mgmt,
        os_version=os_version,
        credential=DeviceCredential(
            username=username,
            password=password,
            ssh_key_path=ssh_key,
        ),
    )

    async def _go() -> None:
        await init_db()
        async for session in get_session():
            await DeviceRepo(session).upsert(dev)
    asyncio.run(_go())
    rprint(f"[green]device registered:[/green] {name} ({vendor.value}) @ {mgmt}")


@app.command()
def render(
    intent_path: Path = typer.Option(..., "--intent", "-f", exists=True, readable=True),
    out: Path = typer.Option(Path("build"), "--out", "-o"),
    inventory: Path | None = typer.Option(None, help="Optional YAML of [Device, ...] to render against."),
) -> None:
    """Render per-device config from an intent file (offline; no store required)."""
    doc = _load_intent(intent_path)
    out.mkdir(parents=True, exist_ok=True)

    if inventory is not None:
        inv_data = yaml.safe_load(inventory.read_text())
        devices = [Device.model_validate(d) for d in inv_data]
    else:
        devices = [
            Device(
                name=n.inventory_ref,
                vendor=Vendor.EOS,  # placeholder; real use should pass an inventory file
                mgmt_address="::1",
                credential=DeviceCredential(username="sdn"),
            )
            for n in doc.fabric.nodes
        ]

    for device in devices:
        bundle = render_device(doc, device)
        path = out / f"{device.name}.cfg"
        path.write_text(bundle.config_text)
        rprint(f"[cyan]rendered[/cyan] {device.vendor} → {path}")


@app.command()
def diff(device: str = typer.Option(...)) -> None:
    """Diff rendered config against running config on a device."""

    async def _go() -> None:
        await init_db()
        async for session in get_session():
            dev = await DeviceRepo(session).get(device)
            if dev is None:
                raise typer.Exit(code=2)
            intent = await IntentRepo(session).load()
            if intent is None:
                raise typer.Exit(code=2)
            bundle = render_device(intent, dev)
            running = await driver_for(dev).fetch_running()
            d = config_diff(running, bundle.config_text)
            if not d:
                rprint(f"[green]{device} in-sync[/green]")
            else:
                rprint(Syntax(d, "diff"))
    asyncio.run(_go())


@app.command()
def push(
    device: str = typer.Option(...),
    confirm: bool = typer.Option(False, "--confirm"),
    timeout: int = typer.Option(120),
) -> None:
    """Push rendered config to a device (requires --confirm)."""
    if not confirm:
        rprint("[red]refusing to push without --confirm[/red]")
        raise typer.Exit(code=2)

    async def _go() -> None:
        await init_db()
        result = await push_device(device, timeout_s=timeout)
        color = "green" if result.ok else "red"
        rprint(f"[{color}]{device}: {result.message}[/{color}]")
    asyncio.run(_go())


@app.command()
def reconcile() -> None:
    """Run one reconcile pass and print a drift table."""

    async def _go() -> None:
        await init_db()
        reports = await reconcile_once()
        table = Table(title="Reconcile report")
        table.add_column("Device")
        table.add_column("Status")
        table.add_column("Drift")
        for r in reports:
            table.add_row(r.device, r.status.value, "yes" if r.diff else "no")
        rprint(table)
    asyncio.run(_go())


if __name__ == "__main__":
    app()
