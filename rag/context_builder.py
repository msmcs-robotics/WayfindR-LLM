"""
Context Builder for WayfindR-LLM
Assembles context for LLM responses from various data sources
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import data sources
try:
    from rag.qdrant_store import get_latest_telemetry, get_all_robots
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    get_latest_telemetry = None
    get_all_robots = None

try:
    from rag.postgresql_store import get_conversation_history, retrieve_relevant
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    get_conversation_history = None
    retrieve_relevant = None

try:
    from core.config import WAYPOINTS, SYSTEM_NAME
except ImportError:
    WAYPOINTS = []
    SYSTEM_NAME = "WayfindR Tour Guide"


class ContextBuilder:
    """Builds context for LLM from multiple data sources"""

    def __init__(self):
        self._cached_robots = []
        self._last_robot_update = None

    def get_active_robots(self, force_refresh: bool = False) -> List[str]:
        """Get list of active robots (with caching)"""
        if not QDRANT_AVAILABLE or not get_all_robots:
            return []

        # Use cache if recent (60 seconds)
        now = datetime.now()
        if (not force_refresh and
            self._last_robot_update and
            (now - self._last_robot_update).seconds < 60):
            return self._cached_robots

        try:
            self._cached_robots = get_all_robots(limit=50)
            self._last_robot_update = now
            return self._cached_robots
        except Exception as e:
            print(f"[CONTEXT] Error getting robots: {e}")
            return self._cached_robots

    def get_robot_status_summary(self) -> str:
        """Get a summary of all robot statuses for context"""
        if not QDRANT_AVAILABLE or not get_latest_telemetry:
            return "Robot status unavailable."

        try:
            latest = get_latest_telemetry()

            if not latest:
                return "No robots currently reporting."

            summaries = []
            for robot_id, telemetry in latest.items():
                status = telemetry.get('status', 'unknown')
                location = telemetry.get('current_location', 'unknown')
                battery = telemetry.get('battery', 0)
                destination = telemetry.get('destination', '')

                summary = f"- {robot_id}: {status} at {location}, battery {battery}%"
                if destination:
                    summary += f", heading to {destination}"

                summaries.append(summary)

            return "\n".join(summaries)

        except Exception as e:
            print(f"[CONTEXT] Error getting robot summary: {e}")
            return "Error retrieving robot status."

    def get_conversation_context(self, conversation_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """Get recent conversation history"""
        if not POSTGRESQL_AVAILABLE or not get_conversation_history:
            return []

        try:
            history = get_conversation_history(conversation_id, limit)
            return history
        except Exception as e:
            print(f"[CONTEXT] Error getting conversation: {e}")
            return []

    def get_relevant_context(self, query: str, limit: int = 3) -> List[Dict]:
        """Get relevant past messages using vector search"""
        if not POSTGRESQL_AVAILABLE or not retrieve_relevant:
            return []

        try:
            return retrieve_relevant(query, limit)
        except Exception as e:
            print(f"[CONTEXT] Error getting relevant context: {e}")
            return []

    def build_system_context(self) -> str:
        """Build system context string for LLM"""
        context_parts = [
            f"System: {SYSTEM_NAME}",
            f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Available waypoints: {', '.join(WAYPOINTS)}"
        ]

        # Add robot status
        robot_summary = self.get_robot_status_summary()
        if robot_summary:
            context_parts.append(f"\nRobot Status:\n{robot_summary}")

        return "\n".join(context_parts)

    def build_full_context(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        robot_id: Optional[str] = None,
        include_history: bool = True,
        include_robots: bool = True
    ) -> Dict[str, Any]:
        """
        Build complete context for LLM response generation

        Args:
            user_message: Current user message
            conversation_id: Optional conversation tracking
            robot_id: Optional robot context
            include_history: Whether to include conversation history
            include_robots: Whether to include robot status

        Returns:
            Dictionary with all context components
        """
        context = {
            "timestamp": datetime.now().isoformat(),
            "system_name": SYSTEM_NAME,
            "waypoints": WAYPOINTS,
            "user_message": user_message,
            "robot_id": robot_id,
            "conversation_id": conversation_id
        }

        # Add robot status
        if include_robots:
            if QDRANT_AVAILABLE and get_latest_telemetry:
                try:
                    if robot_id:
                        latest = get_latest_telemetry(robot_id)
                        context["robot_status"] = latest.get(robot_id, {})
                    else:
                        context["all_robots"] = get_latest_telemetry()
                        context["active_robot_count"] = len(context["all_robots"])
                except Exception as e:
                    print(f"[CONTEXT] Error getting robot status: {e}")

        # Add conversation history
        if include_history:
            history = self.get_conversation_context(conversation_id, limit=5)
            if history:
                context["conversation_history"] = history

        # Add relevant past context
        relevant = self.get_relevant_context(user_message, limit=2)
        if relevant:
            context["relevant_context"] = relevant

        return context


# Global instance
_context_builder = None


def get_context_builder() -> ContextBuilder:
    """Get or create context builder instance"""
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder()
    return _context_builder


__all__ = [
    'ContextBuilder',
    'get_context_builder'
]
