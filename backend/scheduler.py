import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from playlist_manager import playlist_manager
from api.settings import settings

logger = logging.getLogger(__name__)

class PlaylistScheduler:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.scheduler = AsyncIOScheduler()
        self._setup_jobs()
        
    def _setup_jobs(self):
        # Run check once daily at the configured time
        hour, minute = map(int, settings.sync_time.split(':'))
        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self.check_for_updates,
            trigger=trigger,
            id='playlist_sync_check',
            name='Check playlists for updates',
            replace_existing=True
        )
        logger.info(f"PlaylistScheduler jobs setup (Daily at {settings.sync_time})")

    def reschedule_job(self, new_time: str):
        if self.scheduler.get_job('playlist_sync_check'):
            hour, minute = map(int, new_time.split(':'))
            self.scheduler.reschedule_job(
                'playlist_sync_check',
                trigger=CronTrigger(hour=hour, minute=minute)
            )
            logger.info(f"PlaylistScheduler rescheduled to {new_time}")

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("PlaylistScheduler started")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("PlaylistScheduler shutdown")

    async def check_for_updates(self):
        logger.info("Running scheduled playlist update check...")
        playlists = playlist_manager.get_monitored_playlists()
        
        for p in playlists:
            uuid = p['uuid']
            name = p['name']
            frequency = p.get('sync_frequency', 'manual')
            last_sync_str = p.get('last_sync')
            
            if frequency == 'manual':
                continue
                
            should_sync = False
            
            # Logic: If frequency is 'daily', we sync every night.
            # If 'weekly', we check if 7 days passed.
            if frequency == 'daily':
                should_sync = True
            elif frequency == 'weekly':
                 if not last_sync_str:
                     should_sync = True
                 else:
                     try:
                         last_sync = datetime.fromisoformat(last_sync_str)
                         now = datetime.now()
                         if now - last_sync > timedelta(days=7):
                             should_sync = True
                     except Exception:
                         should_sync = True
            elif frequency == 'monthly':
                 if not last_sync_str:
                     should_sync = True
                 else:
                     try:
                         last_sync = datetime.fromisoformat(last_sync_str)
                         now = datetime.now()
                         if now - last_sync > timedelta(days=30):
                             should_sync = True
                     except Exception:
                         should_sync = True
            
            if should_sync:
                logger.info(f"Triggering scheduled sync for playlist: {name} ({frequency})")
                try:
                    await playlist_manager.sync_playlist(uuid)
                except Exception as e:
                    logger.error(f"Scheduled sync failed for {name}: {e}")
            else:
                 pass
