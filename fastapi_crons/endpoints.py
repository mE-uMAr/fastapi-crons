from fastapi import APIRouter, HTTPException, Depends
from .state import StateBackend, SQLiteStateBackend
from .scheduler import Crons
from .config import CronConfig
import asyncio
from datetime import datetime
import inspect
from typing import Optional

def get_cron_router():
    """Get the cron management router with automatic initialization."""
    router = APIRouter()
    
    # Initialize configuration and scheduler
    config = CronConfig()
    crons = Crons(config=config)
    
    async def get_all_jobs():
        if not crons:
            return []
        jobs = crons.get_jobs()
        backend = crons.state_backend
        result = []
        for job in jobs:
            last_run = await backend.get_last_run(job.name)
            status_info = await backend.get_job_status(job.name)
            
            job_data = {
                "name": job.name,
                "expr": job.expr,
                "tags": job.tags,
                "last_run": last_run,
                "next_run": job.next_run.isoformat(),
                "hooks": {
                    "before_run": len(job.before_run_hooks),
                    "after_run": len(job.after_run_hooks),
                    "on_error": len(job.on_error_hooks)
                }
            }
            
            if status_info:
                job_data["status"] = status_info
            
            result.append(job_data)
        return result
    
    @router.get("/system/status")
    async def get_system_status():
        """Get system status and statistics."""
        jobs = crons.get_jobs()
        backend = crons.state_backend
        
        # Count job statuses
        running_count = 0
        failed_count = 0
        completed_count = 0
        
        for job in jobs:
            status_info = await backend.get_job_status(job.name)
            if status_info:
                if status_info['status'] == 'running':
                    running_count += 1
                elif status_info['status'] == 'failed':
                    failed_count += 1
                elif status_info['status'] == 'completed':
                    completed_count += 1
        
        return {
            "instance_id": config.instance_id,
            "total_jobs": len(jobs),
            "running_jobs": running_count,
            "failed_jobs": failed_count,
            "completed_jobs": completed_count,
            "backend_type": type(backend).__name__,
            "distributed_locking": config.enable_distributed_locking,
            "redis_configured": bool(config.redis_url or config.redis_host != "localhost")
        }
    
    @router.get("/")
    async def list_cron_jobs():
        """List all cron jobs with their status."""
        return await get_all_jobs()

    @router.get("/{job_name}")
    async def get_cron_job(job_name: str):
        """Get details for a specific cron job."""
        job = crons.get_job(job_name)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
        
        backend = crons.state_backend
        last_run = await backend.get_last_run(job.name)
        status_info = await backend.get_job_status(job.name)
        
        return {
            "name": job.name,
            "expr": job.expr,
            "tags": job.tags,
            "last_run": last_run,
            "next_run": job.next_run.isoformat(),
            "status": status_info,
            "hooks": {
                "before_run": len(job.before_run_hooks),
                "after_run": len(job.after_run_hooks),
                "on_error": len(job.on_error_hooks)
            }
        }

    @router.get("/{job_name}/status")
    async def get_job_status(job_name: str):
        """Get the current status of a job."""
        backend = crons.state_backend
        status_info = await backend.get_job_status(job_name)
        
        if not status_info:
            raise HTTPException(status_code=404, detail=f"No status found for job '{job_name}'")
        
        # Check if job is locked
        is_locked = await crons.lock_manager.is_locked(f"job:{job_name}")
        status_info["is_locked"] = is_locked
        
        return status_info

    async def execute_hook(hook, job_name: str, context: dict):
        """Execute a hook function, handling both sync and async hooks."""
        try:
            if inspect.iscoroutinefunction(hook):
                await hook(job_name, context)
            else:
                await asyncio.to_thread(hook, job_name, context)
        except Exception as e:
            print(f"[Error][Hook][{job_name}] {e}")

    @router.post("/{job_name}/run")
    async def run_job(job_name: str, force: bool = False):
        """Manually trigger a job execution."""
        job = crons.get_job(job_name)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
        
        # Check if job is locked
        lock_key = f"job:{job_name}"
        if not force and await crons.lock_manager.is_locked(lock_key):
            raise HTTPException(
                status_code=409, 
                detail=f"Job '{job_name}' is currently running on another instance"
            )
        
        # Try to acquire lock
        lock_id = await crons.lock_manager.acquire_lock(lock_key)
        if not lock_id and not force:
            raise HTTPException(
                status_code=409, 
                detail=f"Failed to acquire lock for job '{job_name}'"
            )
        
        try:
            # Set job status
            await crons.state_backend.set_job_status(job_name, "running", config.instance_id)
            
            # Create context for hooks
            context = {
                "job_name": job.name,
                "manual_trigger": True,
                "trigger_time": datetime.now().isoformat(),
                "tags": job.tags,
                "expr": job.expr,
                "instance_id": config.instance_id,
            }
            
            # Execute before_run hooks
            for hook in job.before_run_hooks:
                await execute_hook(hook, job.name, context)
            
            start_time = datetime.now()
            
            try:
                if asyncio.iscoroutinefunction(job.func):
                    result = await job.func()
                else:
                    result = await asyncio.to_thread(job.func)
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                job.last_run = end_time
                await crons.state_backend.set_last_run(job.name, end_time)
                await crons.state_backend.set_job_status(job_name, "completed", config.instance_id)
                
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
                if hasattr(crons.state_backend, 'log_job_execution'):
                    await crons.state_backend.log_job_execution(
                        job_name, config.instance_id, "completed", 
                        start_time, end_time, duration
                    )
                
                return {
                    "status": "success", 
                    "message": f"Job '{job_name}' executed successfully",
                    "execution_time": duration,
                    "instance_id": config.instance_id
                }
                
            except Exception as e:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                error_msg = str(e)
                
                await crons.state_backend.set_job_status(job_name, "failed", config.instance_id)
                
                # Update context with error details
                context.update({
                    "success": False,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": duration,
                    "error": error_msg
                })
                
                # Execute on_error hooks
                for hook in job.on_error_hooks:
                    await execute_hook(hook, job.name, context)
                
                # Log execution if backend supports it
                if hasattr(crons.state_backend, 'log_job_execution'):
                    await crons.state_backend.log_job_execution(
                        job_name, config.instance_id, "failed", 
                        start_time, end_time, duration, error_msg
                    )
                
                raise HTTPException(status_code=500, detail=f"Job execution failed: {error_msg}")
        
        finally:
            # Release lock
            if lock_id:
                await crons.lock_manager.release_lock(lock_key)

    return router
