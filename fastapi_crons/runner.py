import asyncio
import inspect
import logging
from datetime import datetime
from typing import Any
from .state import StateBackend
from .job import CronJob, HookFunc
from .locking import DistributedLockManager
from .config import CronConfig

logger = logging.getLogger("fastapi_cron.runner")

async def execute_hook(hook: HookFunc, job_name: str, context: dict) -> None:
    """Execute a hook function, handling both sync and async hooks."""
    try:
        if inspect.iscoroutinefunction(hook):
            await hook(job_name, context)
        else:
            await asyncio.to_thread(hook, job_name, context)
    except Exception as e:
        logger.error(f"[Hook Error][{job_name}] {e}")

async def run_job_loop(job: CronJob, state: StateBackend, lock_manager: DistributedLockManager, config: CronConfig) -> None:
    """Main job execution loop with distributed locking."""
    logger.info(f"Starting job loop for '{job.name}' - next run at {job.next_run}")
    
    while True:
        try:
            now = datetime.now()
            seconds = (job.next_run - now).total_seconds()
            
            if seconds > 0:
                logger.debug(f"Job '{job.name}' waiting {seconds:.1f} seconds until next run")
                await asyncio.sleep(seconds)

            # Try to acquire distributed lock
            lock_key = f"job:{job.name}"
            lock_id = await lock_manager.acquire_lock(lock_key)
            
            if not lock_id:
                logger.info(f"Job '{job.name}' is locked by another instance, skipping")
                job.update_next_run()
                continue

            try:
                # Set job status to running
                await state.set_job_status(job.name, "running", config.instance_id)
                
                # Create context for hooks
                context: dict[str, Any] = {
                    "job_name": job.name,
                    "scheduled_time": job.next_run.isoformat(),
                    "actual_time": datetime.now().isoformat(),
                    "tags": job.tags,
                    "expr": job.expr,
                    "instance_id": config.instance_id,
                }

                # Execute before_run hooks
                for hook in job.before_run_hooks:
                    await execute_hook(hook, job.name, context)

                start_time = datetime.now()
                error = None
                
                try:
                    logger.info(f"Executing job '{job.name}' on instance {config.instance_id}")
                    
                    if asyncio.iscoroutinefunction(job.func):
                        result = await job.func()
                    else:
                        result = await asyncio.to_thread(job.func)

                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    
                    job.last_run = end_time
                    await state.set_last_run(job.name, end_time)
                    await state.set_job_status(job.name, "completed", config.instance_id)
                    
                    # Update context with execution details
                    context.update({
                        "success": True,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration,
                        "result": result
                    })
                    
                    # Execute after_run hooks
                    for hook in job.after_run_hooks:
                        await execute_hook(hook, job.name, context)
                    
                    # Log execution if backend supports it
                    if hasattr(state, 'log_job_execution'):
                        await state.log_job_execution(
                            job.name, config.instance_id, "completed", 
                            start_time, end_time, duration
                        )
                    
                    logger.info(f"Job '{job.name}' completed successfully in {duration:.2f}s")
                        
                except Exception as e:
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    error = str(e)
                    
                    logger.error(f"Job '{job.name}' failed: {error}")
                    
                    await state.set_job_status(job.name, "failed", config.instance_id)
                    
                    # Update context with error details
                    context.update({
                        "success": False,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration,
                        "error": error
                    })
                    
                    # Execute on_error hooks
                    for hook in job.on_error_hooks:
                        await execute_hook(hook, job.name, context)
                    
                    # Log execution if backend supports it
                    if hasattr(state, 'log_job_execution'):
                        await state.log_job_execution(
                            job.name, config.instance_id, "failed", 
                            start_time, end_time, duration, error
                        )

            finally:
                # Always release the lock
                await lock_manager.release_lock(lock_key)

            job.update_next_run()
            logger.debug(f"Job '{job.name}' next run scheduled for {job.next_run}")
            
        except asyncio.CancelledError:
            logger.info(f"Job loop for '{job.name}' was cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in job loop for '{job.name}': {e}")
            # Wait a bit before retrying to avoid tight error loops
            await asyncio.sleep(60)
