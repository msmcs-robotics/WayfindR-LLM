# context_manager.py - SIMPLIFIED with database manager integration
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from db_manager import get_db_manager
from config_manager import get_config

class ContextManager:
    """Simplified robot context management using database manager"""
    
    def __init__(self):
        self.config = get_config()
        self.db = get_db_manager()
        self._active_robots: Set[str] = set()
        self._robot_cache: Dict[str, Dict] = {}
        self._last_update = datetime.min
        self._running = False
        self._update_lock = asyncio.Lock()  # Add this line
        print("✅ ContextManager initialized")
    
    async def start_background_updates(self):
        """Start background robot context updates"""
        if not self._running:
            self._running = True
            asyncio.create_task(self._update_loop())
            print("🔄 Started robot context background updates")
    
    async def _update_loop(self):
        """Background update loop"""
        while self._running:
            try:
                await self.update_robot_cache()
                await asyncio.sleep(self.config.system.context_update_interval)
            except Exception as e:
                print(f"❌ Context update error: {e}")
                await asyncio.sleep(10)
    
    async def _get_active_robots_uncached(self) -> Set[str]:
        """Get fresh active robots list from DB"""
        try:
            active = self.db.get_active_robots(self.config.system.telemetry_retention_hours)
            return set(active)
        except Exception as e:
            print(f"❌ Error getting active robots: {e}")
            return set()
        
    async def update_robot_cache(self):
        """Update the robot cache with latest telemetry from DB"""
        try:
            active_robots = self.db.get_active_robots(self.config.system.telemetry_retention_hours)
            self._active_robots = set(active_robots)
            self._robot_cache = {}
            for robot_id in self._active_robots:
                telemetry_list = await self.db.get_robot_telemetry(robot_id, limit=1)
                if telemetry_list:
                    self._robot_cache[robot_id] = telemetry_list[0]
            self._last_update = datetime.now()
        except Exception as e:
            print(f"❌ Error updating robot cache: {e}")

    async def get_active_robots(self) -> List[str]:
        """Get cached active robots list with auto-refresh"""
        async with self._update_lock:
            if (datetime.now() - self._last_update).total_seconds() > self.config.system.context_update_interval:
                self._active_robots = await self._get_active_robots_uncached()
                self._last_update = datetime.now()
            return list(self._active_robots)
    
    def get_robot_status(self, robot_id: str) -> Optional[Dict]:
        """Get specific robot status"""
        return self._robot_cache.get(robot_id)
    
    async def build_web_context(self, conversation_id: str, user_id: str, query: str = "", intent_data: dict = None) -> Dict:
        """Build context for web users using db_manager"""
        # Conversation history from DB
        conversation_history = []
        try:
            conversation_history = await self.db.get_conversation_history(conversation_id, limit=self.config.system.chat_history_limit)
        except Exception as e:
            print(f"❌ Error getting conversation history: {e}")

        # Active robots (cached)
        active_robots = await self.get_active_robots()

        # Robot status: just show recent statuses (no search)
        robot_status = list(self._robot_cache.values())[:5]

        return {
            "conversation_history": conversation_history,
            "active_robots": active_robots,
            "robot_status": robot_status
        }
    
    async def build_robot_context(self, conversation_id: str, robot_id: str) -> Dict:
        """Build context for robot users using db_manager"""
        # Conversation history from DB
        conversation_history = []
        try:
            conversation_history = await self.db.get_conversation_history(conversation_id, limit=self.config.system.chat_history_limit)
        except Exception as e:
            print(f"❌ Error getting conversation history: {e}")

        context = {
            "conversation_history": conversation_history,
            "active_robots": [robot_id],
            "robot_status": []
        }
        # Include robot's own status
        own_status = self.get_robot_status(robot_id)
        if own_status:
            context["robot_status"].append(own_status)
        return context
    
    def search_telemetry_by_query(self, query: str, limit: int = 5):
        """Search telemetry using Qdrant full-text search (via db_manager)"""
        # You need to implement this in db_manager if not present
        try:
            return self.db.search_telemetry_by_query(query, limit=limit)
        except Exception as e:
            print(f"❌ Error searching telemetry: {e}")
            return []

# Global instance
_context_manager = None

def get_context_manager() -> ContextManager:
    """Get global context manager instance"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager