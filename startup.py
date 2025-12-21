#!/usr/bin/env python3
"""
WayfindR-LLM Service Coordinator
Manages startup and shutdown of backend services
"""

import subprocess
import sys
import time
import signal
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class ServiceStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


@dataclass
class ServiceConfig:
    name: str
    command: List[str]
    port: Optional[int] = None
    startup_time: float = 2.0


class Service:
    """Manages a single backend service"""

    def __init__(self, config: ServiceConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.status = ServiceStatus.STOPPED

    def start(self) -> bool:
        """Start the service"""
        print(f"[SERVICE] Starting {self.config.name}...")
        self.status = ServiceStatus.STARTING

        try:
            self.process = subprocess.Popen(
                self.config.command,
                stdout=None,
                stderr=None,
                text=True
            )

            time.sleep(0.5)

            if self.process.poll() is not None:
                print(f"[ERROR] {self.config.name} failed to start")
                self.status = ServiceStatus.FAILED
                return False

            if self.config.startup_time > 0.5:
                time.sleep(self.config.startup_time - 0.5)

            self.status = ServiceStatus.RUNNING
            print(f"[SUCCESS] {self.config.name} started (PID: {self.process.pid})")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to start {self.config.name}: {e}")
            self.status = ServiceStatus.FAILED
            return False

    def stop(self):
        """Stop the service"""
        if self.process and self.process.poll() is None:
            print(f"[SHUTDOWN] Stopping {self.config.name}...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                print(f"[SUCCESS] {self.config.name} stopped")
            except subprocess.TimeoutExpired:
                print(f"[WARNING] Force killing {self.config.name}...")
                self.process.kill()
            finally:
                self.status = ServiceStatus.STOPPED

    def is_running(self) -> bool:
        """Check if service is still running"""
        if self.process:
            return self.process.poll() is None
        return False


class ServiceCoordinator:
    """Coordinates multiple backend services"""

    def __init__(self):
        self.services: List[Service] = []
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals"""
        print(f"\n[SIGNAL] Received interrupt signal")
        self.stop_all()
        sys.exit(0)

    def add_service(self, config: ServiceConfig) -> Service:
        """Add a service to be managed"""
        service = Service(config)
        self.services.append(service)
        return service

    def start_all(self) -> bool:
        """Start all services in order"""
        print("=" * 60)
        print("STARTING WAYFIND-R SERVICES")
        print("=" * 60)

        all_started = True
        for service in self.services:
            if not service.start():
                all_started = False
                print(f"[WARNING] Continuing despite {service.config.name} failure")

        return all_started

    def stop_all(self):
        """Stop all services in reverse order"""
        print("\n[SHUTDOWN] Stopping all services...")

        for service in reversed(self.services):
            service.stop()

        print("[SHUTDOWN] All services stopped")

    def monitor(self):
        """Monitor services and keep running"""
        print("\n" + "=" * 60)
        print("WAYFIND-R SERVICES RUNNING")
        print("=" * 60)
        print("\nPress Ctrl+C to shutdown\n")

        try:
            while True:
                for service in self.services:
                    if service.status == ServiceStatus.RUNNING and not service.is_running():
                        print(f"[ERROR] {service.config.name} has stopped unexpectedly!")
                        service.status = ServiceStatus.FAILED

                time.sleep(1)
        except KeyboardInterrupt:
            pass


def check_dependencies() -> bool:
    """Verify required packages are installed"""
    print("[CHECK] Verifying dependencies...")

    required = ['fastapi', 'uvicorn', 'psycopg2', 'qdrant_client', 'sentence_transformers']
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"[INFO] Install with: pip install {' '.join(missing)}")
        return False

    print("[SUCCESS] All dependencies found")
    return True


def check_docker() -> bool:
    """Verify Docker containers are running"""
    print("[CHECK] Verifying Docker containers...")

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )

        containers = result.stdout.strip().split('\n')

        pg_running = any('wayfind_pg' in c for c in containers)
        qdrant_running = any('wayfind_qdrant' in c for c in containers)

        if not pg_running:
            print("[WARNING] PostgreSQL container not running")
        if not qdrant_running:
            print("[WARNING] Qdrant container not running")

        if not pg_running or not qdrant_running:
            print("[INFO] Start with: docker compose up -d")
            return False

        print("[SUCCESS] Docker containers running")
        return True

    except Exception as e:
        print(f"[WARNING] Could not check Docker: {e}")
        return False


def main():
    """Main entry point"""

    # Pre-flight checks
    if not check_dependencies():
        print("\n[INFO] Some dependencies missing, but continuing...")

    check_docker()

    # Create service coordinator
    coordinator = ServiceCoordinator()

    # Add MCP Chatapp Service
    coordinator.add_service(ServiceConfig(
        name="WayfindR MCP Server",
        command=[sys.executable, "main.py"],
        port=5000,
        startup_time=3.0
    ))

    # Start all services
    if not coordinator.start_all():
        print("\n[WARNING] Some services failed to start")
    else:
        print("\n[SUCCESS] All services started!")

    # Show access information
    print("\n" + "=" * 60)
    print("SERVICE ACCESS POINTS")
    print("=" * 60)
    print("  Dashboard:    http://localhost:5000")
    print("  Chat API:     POST http://localhost:5000/chat")
    print("  Telemetry:    POST http://localhost:5000/telemetry")
    print("  Health:       GET http://localhost:5000/health")
    print("=" * 60 + "\n")

    # Monitor services
    coordinator.monitor()

    # Cleanup
    coordinator.stop_all()


if __name__ == "__main__":
    main()
