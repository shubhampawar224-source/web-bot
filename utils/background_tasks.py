# utils/background_tasks.py

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from enum import Enum
from database.db import SessionLocal
from model.models import Website, Firm
from utils.scraper import build_about
from utils.vector_store import chunk_text, add_text_chunks_to_collection

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 3):
        self.tasks: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self.max_concurrent_tasks = max_concurrent_tasks
        self._processing_semaphore = asyncio.Semaphore(max_concurrent_tasks)
    
    async def create_task(self, url: str, session_id: str = None, injected_by: str = "user") -> str:
        """Create a new background task and return task ID"""
        task_id = str(uuid.uuid4())
        
        async with self._lock:
            self.tasks[task_id] = {
                "id": task_id,
                "url": url,
                "status": TaskStatus.PENDING.value,
                "progress": 0,
                "message": "Task created",
                "created_at": datetime.now(),
                "session_id": session_id,
                "injected_by": injected_by,
                "result": None,
                "error": None
            }
        
        # Start the background task
        asyncio.create_task(self._process_url_task(task_id))
        
        return task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get current status of a task"""
        async with self._lock:
            return self.tasks.get(task_id)
    
    async def _update_task(self, task_id: str, **updates):
        """Update task with new information"""
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(updates)
    
    async def _process_url_task(self, task_id: str):
        """Background task to process URL injection with concurrency control"""
        async with self._processing_semaphore:  # Limit concurrent processing
            try:
                task = self.tasks[task_id]
                url = task["url"]
                session_id = task["session_id"]
                injected_by = task["injected_by"]
                
                # Update status to processing
                await self._update_task(task_id, 
                    status=TaskStatus.PROCESSING.value, 
                    progress=10, 
                    message="Starting URL processing..."
                )
                
                # Check if URL already exists
                db = SessionLocal()
                try:
                    existing_site = db.query(Website).filter(Website.base_url == url).first()
                    if existing_site:
                        firm_name = existing_site.firm.name if existing_site.firm else "Unknown"
                        await self._update_task(task_id,
                            status=TaskStatus.FAILED.value,
                            progress=100,
                            message=f"URL already exists in database (Firm: {firm_name})",
                            error="URL_EXISTS"
                        )
                        return
                finally:
                    db.close()
                
                # Update progress
                await self._update_task(task_id, progress=20, message="Scraping website content...")
                
                # Scrape the website
                about_obj = await build_about(url)
                
                if not about_obj:
                    await self._update_task(task_id,
                        status=TaskStatus.FAILED.value,
                        progress=100,
                        message="Failed to scrape content from the URL",
                        error="SCRAPE_FAILED"
                    )
                    return
                
                # Update progress
                await self._update_task(task_id, progress=60, message="Processing content...")
                
                full_text = about_obj.get("full_text", "").strip()
                if not full_text:
                    await self._update_task(task_id,
                        status=TaskStatus.FAILED.value,
                        progress=100,
                        message="No text content found on the webpage",
                        error="NO_CONTENT"
                    )
                    return
                
                # Update progress
                await self._update_task(task_id, progress=80, message="Adding to knowledge base...")
                
                # Process and store the content
                chunks = chunk_text(full_text)
                metadata = {
                    "type": "website",
                    "url": url,
                    "firm_name": about_obj.get("firm_name"),
                    "session_id": session_id or "global",
                    "injected_by": injected_by,
                    "task_id": task_id
                }
                
                # Add to vector database (this runs in a separate thread to avoid blocking)
                await asyncio.get_event_loop().run_in_executor(
                    None, add_text_chunks_to_collection, chunks, metadata
                )
                
                # Task completed successfully
                result = {
                    "url": url,
                    "firm_name": about_obj.get("firm_name"),
                    "firm_id": about_obj.get("firm_id"),
                    "indexed_chunks": len(chunks),
                    "injected_by": injected_by
                }
                
                await self._update_task(task_id,
                    status=TaskStatus.COMPLETED.value,
                    progress=100,
                    message=f"Successfully processed and added {len(chunks)} content chunks to knowledge base",
                    result=result
                )
                
            except Exception as e:
                await self._update_task(task_id,
                    status=TaskStatus.FAILED.value,
                    progress=100,
                    message=f"Failed to process URL: {str(e)}",
                    error=str(e)
                )
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove old completed/failed tasks to free memory"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        async with self._lock:
            to_remove = []
            for task_id, task in self.tasks.items():
                if (task["created_at"] < cutoff_time and 
                    task["status"] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]):
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
        
        if to_remove:
            print(f"[TaskManager] Cleaned up {len(to_remove)} old tasks")

# Global task manager instance
task_manager = TaskManager()

# Cleanup task that runs periodically
async def periodic_cleanup():
    """Background task to periodically clean up old tasks"""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        await task_manager.cleanup_old_tasks()

# Start cleanup task when module is imported
asyncio.create_task(periodic_cleanup())