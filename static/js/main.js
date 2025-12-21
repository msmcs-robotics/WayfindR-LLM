/**
 * main.js - Application Initialization for WayfindR Dashboard
 */

(function() {
    'use strict';

    async function initializeDashboard() {
        DashboardUtils.log('INIT', '=== Starting WayfindR Tour Guide Dashboard ===');

        try {
            DashboardUtils.log('INIT', 'Step 1: Initializing DOM references...');
            const domReady = DashboardState.initializeDOMReferences();

            if (!domReady) {
                DashboardUtils.error('INIT', 'Failed to initialize DOM references.');
                showErrorMessage('Failed to initialize dashboard. Please check console.');
                return;
            }

            DashboardUtils.log('INIT', 'Step 2: Setting up event listeners...');
            StreamManager.setupEventListeners();
            ChatManager.setupEventListeners();

            DashboardUtils.log('INIT', 'Step 3: Starting health monitoring...');
            HealthMonitor.startMonitoring(10000);

            DashboardUtils.log('INIT', 'Step 4: Initializing streaming...');
            await StreamManager.initialize();

            DashboardUtils.log('INIT', '=== Dashboard initialization complete ===');

        } catch (error) {
            DashboardUtils.error('INIT', 'Fatal error during initialization', error);
            showErrorMessage(`Initialization failed: ${error.message}`);
        }
    }

    function showErrorMessage(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            z-index: 10000;
            max-width: 400px;
        `;
        errorDiv.innerHTML = `
            <strong>Error</strong><br>
            ${DashboardUtils.escapeHtml(message)}
        `;
        document.body.appendChild(errorDiv);

        setTimeout(() => {
            if (errorDiv.parentNode) {
                document.body.removeChild(errorDiv);
            }
        }, 10000);
    }

    function checkModules() {
        const requiredModules = [
            'DashboardUtils',
            'DashboardState',
            'HealthMonitor',
            'LogManager',
            'StreamManager',
            'ChatManager'
        ];

        const missingModules = requiredModules.filter(module => !window[module]);

        if (missingModules.length > 0) {
            console.error('[INIT] Missing required modules:', missingModules);
            showErrorMessage(`Missing modules: ${missingModules.join(', ')}`);
            return false;
        }

        return true;
    }

    document.addEventListener('DOMContentLoaded', function() {
        DashboardUtils.log('INIT', 'DOM Content Loaded');

        if (!checkModules()) {
            DashboardUtils.error('INIT', 'Not all modules loaded.');
            return;
        }

        initializeDashboard();
    });

    window.addEventListener('load', function() {
        if (!DashboardState.postgresql.container) {
            DashboardUtils.log('INIT', 'Retrying initialization on window load...');
            if (checkModules()) {
                initializeDashboard();
            }
        }
    });

    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            DashboardUtils.log('INIT', 'Page hidden - pausing operations');
        } else {
            DashboardUtils.log('INIT', 'Page visible - resuming operations');
            HealthMonitor.checkSystemHealth();
        }
    });

    window.addEventListener('error', function(event) {
        DashboardUtils.error('GLOBAL', 'Uncaught error', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno
        });
    });

    window.addEventListener('unhandledrejection', function(event) {
        DashboardUtils.error('GLOBAL', 'Unhandled promise rejection', {
            reason: event.reason
        });
    });

    DashboardUtils.log('INIT', 'Main script loaded and ready');

})();
