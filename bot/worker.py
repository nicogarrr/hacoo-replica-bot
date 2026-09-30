"""Do not close SQLite/session resources while a to_thread worker still uses them."""
import asyncio

async def drain_worker(fn,*args,**kwargs):
    task=asyncio.create_task(asyncio.to_thread(fn,*args,**kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling an asyncio wrapper does not stop the underlying thread.
        # Drain it before releasing DB/session. Domain functions remain bounded.
        try:
            await task
        finally:
            raise
