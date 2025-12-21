/**
 * logs.js - Log Display Management for WayfindR Dashboard
 */

const LogManager = {
    MAX_LOGS: 200,

    createLogElement: function(log, source) {
        const div = document.createElement('div');
        div.className = 'log-message';
        div.dataset.logId = log.log_id || log.id || DashboardUtils.generateId(source);
        div.dataset.source = source;

        const metadata = log.metadata || {};
        const timestamp = metadata.timestamp || log.created_at || new Date().toISOString();
        const robotId = metadata.robot_id || 'System';
        const text = log.text || '';
        const status = metadata.status || '';
        const battery = metadata.battery;
        const location = metadata.current_location || '';

        // Add status-based styling
        if (status === 'stuck') div.classList.add('stuck-log');
        if (status === 'navigating') div.classList.add('navigating-log');

        // Build robot info if available
        let robotInfo = '';
        if (battery !== undefined || location || status) {
            robotInfo = '<div class="robot-info">';
            if (status) {
                const statusClass = status === 'stuck' ? 'stuck' : (status === 'idle' ? 'idle' : 'navigating');
                robotInfo += `<span class="robot-metric log-status ${statusClass}">${status}</span>`;
            }
            if (battery !== undefined) {
                const batteryClass = battery < 20 ? 'low' : '';
                robotInfo += `<span class="robot-metric log-battery ${batteryClass}">Battery: ${battery}%</span>`;
            }
            if (location) {
                robotInfo += `<span class="robot-metric log-location">${DashboardUtils.escapeHtml(location)}</span>`;
            }
            robotInfo += '</div>';
        }

        // Build metadata display
        let metaHtml = '';
        if (log.log_id) {
            const shortId = String(log.log_id).substring(0, 8);
            metaHtml += `<span class="log-id">#${shortId}</span>`;
        }

        div.innerHTML = `
            <div class="log-header">
                <strong>${DashboardUtils.escapeHtml(String(robotId))}</strong>
                <span class="log-time">${DashboardUtils.formatTimestamp(timestamp)}</span>
            </div>
            <div class="log-body">${DashboardUtils.escapeHtml(String(text))}</div>
            ${robotInfo}
            <div class="log-meta">${metaHtml}</div>
        `;

        return div;
    },

    addLog: function(source, log) {
        const streamState = DashboardState.getStreamState(source);
        const logId = log.log_id || log.id || DashboardUtils.generateId(source);

        if (streamState.logs.has(logId)) return;
        streamState.logs.add(logId);

        const logElement = this.createLogElement(log, source);
        streamState.container.prepend(logElement);

        while (streamState.container.children.length > this.MAX_LOGS) {
            const removed = streamState.container.removeChild(streamState.container.lastChild);
            const removedId = removed.dataset.logId;
            if (removedId) streamState.logs.delete(removedId);
        }

        DashboardState.updateCount(source, streamState.logs.size);

        const countBadge = document.getElementById(source === 'postgresql' ? 'pg-count' : 'qdrant-count');
        if (countBadge) {
            countBadge.classList.toggle('at-limit', streamState.logs.size >= this.MAX_LOGS);
            countBadge.title = streamState.logs.size >= this.MAX_LOGS
                ? `Showing ${this.MAX_LOGS} most recent`
                : '';
        }

        if (streamState.container.scrollTop < 100) {
            streamState.container.scrollTop = 0;
        }
    },

    loadInitialData: async function(source) {
        DashboardUtils.log('LOGS', `Loading ${source} logs...`);

        try {
            const response = await fetch(`/data/${source}`);
            const data = await response.json();

            if (data && data.length > 0) {
                const streamState = DashboardState.getStreamState(source);
                streamState.container.innerHTML = '';

                const logsToShow = data.slice(0, this.MAX_LOGS);
                logsToShow.forEach(log => this.addLog(source, log));

                DashboardUtils.log('LOGS', `Loaded ${logsToShow.length} ${source} logs`);
            } else {
                DashboardUtils.log('LOGS', `No ${source} logs yet`);
                this.updateLoadingStatus(source, 'No data yet', false);
            }
        } catch (error) {
            DashboardUtils.error('LOGS', `Failed to load ${source}`, error);
            this.updateLoadingStatus(source, 'Failed to load', true);
        }
    },

    updateLoadingStatus: function(source, message, isError) {
        const loadingElement = document.getElementById(
            source === 'postgresql' ? 'pg-loading' : 'qdrant-loading'
        );
        if (loadingElement) {
            loadingElement.textContent = message;
            loadingElement.classList.toggle('error', isError);
            loadingElement.classList.toggle('active', !isError);
        }
    }
};

window.LogManager = LogManager;
