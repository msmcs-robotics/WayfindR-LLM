/**
 * streaming.js - Real-time Stream Management for WayfindR Dashboard
 */

const StreamManager = {
    startStream: function(source) {
        const streamState = DashboardState.getStreamState(source);
        const endpoint = `/stream/${source}`;

        DashboardUtils.log('STREAM', `Starting ${source} stream from ${endpoint}...`);

        if (streamState.eventSource) {
            streamState.eventSource.close();
        }

        streamState.eventSource = new EventSource(endpoint);
        streamState.streaming = true;

        this.updateStreamButton(source, true);

        streamState.eventSource.onmessage = (event) => {
            try {
                const log = JSON.parse(event.data);

                if (!log || (log.error && !log.log_id)) {
                    return;
                }

                LogManager.addLog(source, log);
            } catch (error) {
                DashboardUtils.error('STREAM', `Error parsing ${source} stream data`, error);
            }
        };

        streamState.eventSource.onerror = (error) => {
            DashboardUtils.error('STREAM', `${source} stream error`, error);

            if (streamState.eventSource.readyState === EventSource.CONNECTING) {
                LogManager.updateLoadingStatus(source, 'Reconnecting...', false);
            } else if (streamState.eventSource.readyState === EventSource.CLOSED) {
                LogManager.updateLoadingStatus(source, 'Stream disconnected, retrying...', true);

                streamState.eventSource.close();

                setTimeout(() => {
                    if (streamState.streaming) {
                        DashboardUtils.log('STREAM', `Attempting to reconnect ${source}...`);
                        this.startStream(source);
                    }
                }, 3000);
            }
        };

        streamState.eventSource.onopen = () => {
            DashboardUtils.log('STREAM', `${source} stream connected`);
            LogManager.updateLoadingStatus(source, 'Live streaming', false);
            HealthMonitor.updateStatusIndicator(source, 'online');
        };
    },

    stopStream: function(source) {
        const streamState = DashboardState.getStreamState(source);

        DashboardUtils.log('STREAM', `Stopping ${source} stream...`);

        if (streamState.eventSource) {
            streamState.eventSource.close();
            streamState.eventSource = null;
        }

        streamState.streaming = false;

        this.updateStreamButton(source, false);

        LogManager.updateLoadingStatus(source, 'Stream paused', false);
    },

    toggleStream: function(source) {
        const streamState = DashboardState.getStreamState(source);

        if (streamState.streaming) {
            this.stopStream(source);
        } else {
            this.startStream(source);
        }
    },

    updateStreamButton: function(source, isActive) {
        const streamState = DashboardState.getStreamState(source);

        if (isActive) {
            streamState.toggle.classList.add('active');
            streamState.toggle.innerHTML = '<span class="stream-icon">Live</span>';
        } else {
            streamState.toggle.classList.remove('active');
            streamState.toggle.innerHTML = '<span class="stream-icon">Start Live</span>';
        }
    },

    setupEventListeners: function() {
        DashboardUtils.log('STREAM', 'Setting up stream event listeners...');

        DashboardState.postgresql.toggle.addEventListener('click', () => {
            this.toggleStream('postgresql');
        });

        DashboardState.qdrant.toggle.addEventListener('click', () => {
            this.toggleStream('qdrant');
        });
    },

    initialize: async function() {
        DashboardUtils.log('STREAM', 'Initializing streaming...');

        await LogManager.loadInitialData('postgresql');
        await LogManager.loadInitialData('qdrant');

        setTimeout(() => {
            DashboardUtils.log('STREAM', 'Auto-starting live streams...');
            this.startStream('postgresql');
            this.startStream('qdrant');
        }, 1000);
    }
};

window.StreamManager = StreamManager;
