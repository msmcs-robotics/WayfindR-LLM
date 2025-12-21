/**
 * health.js - System Health Monitoring for WayfindR Dashboard
 */

const HealthMonitor = {
    updateStatusIndicator: function(source, status) {
        let indicatorId, textId;

        if (source === 'postgresql') {
            indicatorId = 'pg-status';
            textId = 'pg-status-text';
        } else if (source === 'qdrant') {
            indicatorId = 'qdrant-status';
            textId = 'qdrant-status-text';
        } else if (source === 'robots') {
            indicatorId = 'robot-status';
            textId = 'robot-status-text';
        } else if (source === 'llm') {
            indicatorId = 'llm-status';
            textId = 'llm-status-text';
        }

        const indicator = document.getElementById(indicatorId);
        const text = document.getElementById(textId);

        if (indicator) {
            indicator.className = `status-indicator ${status}`;
        }

        if (text) {
            text.textContent = status === 'online' ? 'Online' : 'Offline';
        }

        DashboardState.health[source] = status;
    },

    checkSystemHealth: async function() {
        try {
            const response = await fetch('/health');
            const health = await response.json();

            DashboardUtils.log('HEALTH', 'Health check response:', health);

            // PostgreSQL status
            this.updateStatusIndicator('postgresql', 'online');

            // Qdrant status
            if (health.qdrant === 'available') {
                this.updateStatusIndicator('qdrant', 'online');
            } else {
                this.updateStatusIndicator('qdrant', 'offline');
            }

            // Robot status
            if (health.active_robots && health.active_robots > 0) {
                this.updateStatusIndicator('robots', 'online');
            } else {
                this.updateStatusIndicator('robots', 'offline');
            }

            // LLM status
            if (health.llm === 'ready') {
                this.updateStatusIndicator('llm', 'online');
            } else {
                this.updateStatusIndicator('llm', 'offline');
            }

        } catch (error) {
            DashboardUtils.error('HEALTH', 'Health check failed', error);
            this.updateStatusIndicator('postgresql', 'offline');
            this.updateStatusIndicator('qdrant', 'offline');
            this.updateStatusIndicator('robots', 'offline');
            this.updateStatusIndicator('llm', 'offline');
        }
    },

    startMonitoring: function(interval = 10000) {
        DashboardUtils.log('HEALTH', `Starting health monitoring (interval: ${interval}ms)`);

        this.checkSystemHealth();

        setInterval(() => {
            this.checkSystemHealth();
        }, interval);
    }
};

window.HealthMonitor = HealthMonitor;
