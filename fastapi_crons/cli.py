import asyncio
import inspect
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import CronConfig
from .locking import DistributedLockManager, LocalLockBackend, RedisLockBackend
from .state import RedisStateBackend, SQLiteStateBackend

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

console = Console()
cli = typer.Typer(help="FastAPI Crons CLI - Manage your cron jobs")

# Global configuration
config = CronConfig()
state_backend = None
lock_manager = None

def get_state_backend():
    """Get the appropriate state backend based on configuration."""
    global state_backend
    if state_backend is None:
        if config.redis_url or config.enable_distributed_locking:
            if not REDIS_AVAILABLE:
                console.print("[red]Redis not available. Install with: pip install redis[/red]")
                return
            try:
                redis_client = redis.from_url(config.redis_url) if config.redis_url else redis.Redis(
                    host=config.redis_host,
                    port=config.redis_port,
                    db=config.redis_db,
                    password=config.redis_password
                )
                state_backend = RedisStateBackend(redis_client)
            except Exception as e:
                console.print(f"[yellow]Error connecting to Redis: {e}, falling back to SQLite[/yellow]")
                state_backend = SQLiteStateBackend(config.sqlite_db_path)
        else:
            state_backend = SQLiteStateBackend(config.sqlite_db_path)
    return state_backend

def get_lock_manager():
    """Get the appropriate lock manager based on configuration."""
    global lock_manager
    if lock_manager is None:
        if config.enable_distributed_locking and (config.redis_url or config.redis_host):
            if not REDIS_AVAILABLE:
                console.print("[red]Redis not available. Install with: pip install redis[/red]")
                return
            try:
                redis_client = redis.from_url(config.redis_url) if config.redis_url else redis.Redis(
                    host=config.redis_host,
                    port=config.redis_port,
                    db=config.redis_db,
                    password=config.redis_password
                )
                lock_backend = RedisLockBackend(redis_client)
            except Exception as e:
                console.print(f"[yellow]Error connecting to Redis: {e}, using local locking: {e}[/yellow]")
                lock_backend = LocalLockBackend()
        else:
            lock_backend = LocalLockBackend()

        lock_manager = DistributedLockManager(lock_backend, config)
    return lock_manager

@cli.command()
def config_set(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value")
):
    """Set configuration values."""
    global config

    if hasattr(config, key):
        # Convert value to appropriate type
        current_value = getattr(config, key)
        if isinstance(current_value, bool):
            value = value.lower() in ('true', '1', 'yes', 'on')
        elif isinstance(current_value, int):
            value = int(value)

        setattr(config, key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    else:
        console.print(f"[red]Unknown configuration key: {key}[/red]")
        console.print("Available keys:", list(config.__dict__.keys()))

@cli.command()
def config_show():
    """Show current configuration."""
    table = Table(title="Current Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, value in config.__dict__.items():
        table.add_row(key, str(value))

    console.print(table)

@cli.command()
def list_jobs():
    """List all registered jobs and their status."""
    async def run():
        backend = get_state_backend()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Loading jobs...", total=None)

            try:
                jobs = await backend.get_all_jobs()
                progress.remove_task(task)

                if not jobs:
                    console.print("[yellow]No jobs found[/yellow]")
                    return

                table = Table(title="Registered Cron Jobs")
                table.add_column("Job Name", style="cyan")
                table.add_column("Last Run", style="green")
                table.add_column("Status", style="yellow")

                for job_name, last_run in jobs:
                    last_run_str = last_run if last_run else "Never"

                    # Get job status
                    status_info = await backend.get_job_status(job_name)
                    status = "Unknown"
                    if status_info:
                        status = f"{status_info['status']} ({status_info['instance_id']})"

                    table.add_row(job_name, last_run_str, status)

                console.print(table)

            except Exception as e:
                progress.remove_task(task)
                console.print(f"[red]Error loading jobs: {e}[/red]")

    asyncio.run(run())

async def execute_hook(hook, job_name: str, context: dict):
    """Execute a hook function, handling both sync and async hooks."""
    try:
        if inspect.iscoroutinefunction(hook):
            await hook(job_name, context)
        else:
            await asyncio.to_thread(hook, job_name, context)
    except Exception as e:
        console.print(f"[red][Hook Error][{job_name}] {e}[/red]")

@cli.command()
def run_job(
    name: str = typer.Argument(..., help="Job name to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Force run even if locked")
):
    """Manually run a specific job."""
    async def run():
        from .scheduler import Crons

        backend = get_state_backend()
        lock_mgr = get_lock_manager()

        crons = Crons(state_backend=backend, lock_manager=lock_mgr, config=config)
        jobs = crons.get_jobs()

        target_job = None
        for job in jobs:
            if job.name == name:
                target_job = job
                break

        if not target_job:
            console.print(f"[red]Job '{name}' not found[/red]")
            available_jobs = [job.name for job in jobs]
            if available_jobs:
                console.print("Available jobs:", ", ".join(available_jobs))
            return

        # Check if job is locked
        if not force and await lock_mgr.is_locked(f"job:{name}"):
            console.print(f"[yellow]Job '{name}' is currently locked (running on another instance)[/yellow]")
            console.print("Use --force to override (not recommended)")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Running job '{name}'...", total=None)

            try:
                # Acquire lock
                lock_id = await lock_mgr.acquire_lock(f"job:{name}")
                if not lock_id and not force:
                    progress.remove_task(task)
                    console.print(f"[red]Failed to acquire lock for job '{name}'[/red]")
                    return

                # Set job status
                await backend.set_job_status(name, "running", config.instance_id)

                # Create context for hooks
                context = {
                    "job_name": target_job.name,
                    "manual_trigger": True,
                    "trigger_time": datetime.now(timezone.utc).isoformat(),
                    "tags": target_job.tags,
                    "expr": target_job.expr,
                }

                # Execute before_run hooks
                for hook in target_job.before_run_hooks:
                    await execute_hook(hook, target_job.name, context)

                start_time = datetime.now(timezone.utc)

                try:
                    if asyncio.iscoroutinefunction(target_job.func):
                        result = await target_job.func()
                    else:
                        result = await asyncio.to_thread(target_job.func)

                    end_time = datetime.now(timezone.utc)
                    duration = (end_time - start_time).total_seconds()

                    # Update last run
                    target_job.last_run = end_time
                    await backend.set_last_run(target_job.name, end_time)
                    await backend.set_job_status(name, "completed", config.instance_id)

                    # Update context with execution details
                    context.update({
                        "success": True,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration,
                        "result": result
                    })

                    # Execute after_run hooks
                    for hook in target_job.after_run_hooks:
                        await execute_hook(hook, target_job.name, context)

                    # Log execution
                    await backend.log_job_execution(
                        name, config.instance_id, "completed",
                        start_time, end_time, duration
                    )

                    progress.remove_task(task)
                    console.print(f"[green]✓ Job '{name}' completed successfully in {duration:.2f}s[/green]")

                except Exception as e:
                    end_time = datetime.now(timezone.utc)
                    duration = (end_time - start_time).total_seconds()
                    error_msg = str(e)

                    await backend.set_job_status(name, "failed", config.instance_id)

                    # Update context with error details
                    context.update({
                        "success": False,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration,
                        "error": error_msg
                    })

                    # Execute on_error hooks
                    for hook in target_job.on_error_hooks:
                        await execute_hook(hook, target_job.name, context)

                    # Log execution
                    await backend.log_job_execution(
                        name, config.instance_id, "failed",
                        start_time, end_time, duration, error_msg
                    )

                    progress.remove_task(task)
                    console.print(f"[red]✗ Job '{name}' failed after {duration:.2f}s: {error_msg}[/red]")

            finally:
                # Release lock
                if lock_id:
                    await lock_mgr.release_lock(f"job:{name}")

    asyncio.run(run())

@cli.command()
def status():
    """Show overall system status."""
    async def run():
        backend = get_state_backend()
        _ = get_lock_manager()  # Initialize lock manager for status display

        # System info panel
        system_info = f"""
[bold]Instance ID:[/bold] {config.instance_id}
[bold]Backend:[/bold] {type(backend).__name__}
[bold]Locking:[/bold] {'Distributed' if config.enable_distributed_locking else 'Local'}
[bold]Redis URL:[/bold] {config.redis_url or 'Not configured'}
        """

        console.print(Panel(system_info.strip(), title="System Status", border_style="blue"))

        # Job statistics
        try:
            jobs = await backend.get_all_jobs()
            running_jobs = 0
            failed_jobs = 0

            for job_name, _ in jobs:
                status_info = await backend.get_job_status(job_name)
                if status_info:
                    if status_info['status'] == 'running':
                        running_jobs += 1
                    elif status_info['status'] == 'failed':
                        failed_jobs += 1

            stats = f"""
[bold]Total Jobs:[/bold] {len(jobs)}
[bold]Running:[/bold] {running_jobs}
[bold]Failed:[/bold] {failed_jobs}
            """

            console.print(Panel(stats.strip(), title="Job Statistics", border_style="green"))

        except Exception as e:
            console.print(f"[red]Error getting status: {e}[/red]")

    asyncio.run(run())

@cli.command()
def start_scheduler(
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level")
):
    """Start the cron scheduler."""
    import logging

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def run():
        from .scheduler import Crons

        backend = get_state_backend()
        lock_mgr = get_lock_manager()

        console.print(f"[green]Starting cron scheduler (Instance: {config.instance_id})[/green]")

        crons = Crons(state_backend=backend, lock_manager=lock_mgr, config=config)

        if not crons.get_jobs():
            console.print("[yellow]No jobs registered. Make sure to import your job modules.[/yellow]")
        else:
            console.print(f"[blue]Loaded {len(crons.get_jobs())} jobs[/blue]")

        try:
            # Start the scheduler
            await crons.start()

            if daemon:
                # Run indefinitely
                while True:
                    await asyncio.sleep(60)
            else:
                console.print("[green]Scheduler started. Press Ctrl+C to stop.[/green]")
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Stopping scheduler...[/yellow]")

        finally:
            await crons.stop()
            console.print("[green]Scheduler stopped[/green]")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")

@cli.command()
def logs(
    job_name: str | None = typer.Option(None, "--job", "-j", help="Filter by job name"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of log entries to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output")
):
    """Show job execution logs."""
    async def run():
        _ = get_state_backend()  # Ensure backend is available

        # TODO: Implement get_execution_logs method in state backends
        # For now, show a placeholder message
        console.print("[yellow]Log viewing feature coming soon[/yellow]")

    asyncio.run(run())

if __name__ == "__main__":
    cli()
