/**
 * chat.js - Chat Interface Management for WayfindR Dashboard
 */

const ChatManager = {
    addChatMessage: function(message, type = 'bot', status = '') {
        const div = document.createElement('div');
        div.className = `${type}-message`;

        if (status) {
            div.classList.add(`message-${status}`);
            const statusIcon = status === 'success' ? '>' :
                             status === 'error' ? '!' : 'i';
            div.innerHTML = `<span class="status-indicator-msg">${statusIcon}</span>${DashboardUtils.escapeHtml(String(message))}`;
        } else {
            const formatted = this.formatMessage(message);
            div.innerHTML = formatted;
        }

        DashboardState.chat.container.appendChild(div);
        DashboardState.chat.container.scrollTop = DashboardState.chat.container.scrollHeight;

        return div;
    },

    formatMessage: function(text) {
        let formatted = DashboardUtils.escapeHtml(String(text));

        formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/`(.+?)`/g, '<code>$1</code>');
        formatted = formatted.replace(/^- (.+)$/gm, '<li>$1</li>');
        formatted = formatted.replace(/(<li>.*<\/li>)+/g, '<ul>$&</ul>');
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    },

    handleChatSubmit: async function(event) {
        event.preventDefault();

        const userInput = DashboardState.chat.input.value.trim();
        if (!userInput) return;

        DashboardUtils.log('CHAT', 'Sending message:', userInput);

        this.addChatMessage(userInput, 'user');
        DashboardState.chat.input.value = '';

        const loadingMsg = this.addChatMessage('Processing...', 'bot');

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userInput })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            DashboardUtils.log('CHAT', 'Received response:', data);

            if (loadingMsg.parentNode === DashboardState.chat.container) {
                DashboardState.chat.container.removeChild(loadingMsg);
            }

            let status = '';
            const responseText = data.response || 'No response received';

            if (data.error || responseText.toLowerCase().includes('error')) {
                status = 'error';
            }

            this.addChatMessage(responseText, 'bot', status);

        } catch (error) {
            DashboardUtils.error('CHAT', 'Error sending message', error);

            if (loadingMsg.parentNode === DashboardState.chat.container) {
                DashboardState.chat.container.removeChild(loadingMsg);
            }

            this.addChatMessage(`Error: ${error.message}`, 'bot', 'error');
        }
    },

    clearChat: function() {
        const welcomeMsg = DashboardState.chat.container.querySelector('.welcome-message');
        DashboardState.chat.container.innerHTML = '';

        if (welcomeMsg) {
            DashboardState.chat.container.appendChild(welcomeMsg);
        }

        this.addChatMessage('Chat cleared', 'bot');
    },

    setupEventListeners: function() {
        DashboardUtils.log('CHAT', 'Setting up chat event listeners...');

        DashboardState.chat.form.addEventListener('submit', (e) => {
            this.handleChatSubmit(e);
        });

        const clearChatBtn = document.getElementById('clear-chat');
        if (clearChatBtn) {
            clearChatBtn.addEventListener('click', () => this.clearChat());
        }
    }
};

window.ChatManager = ChatManager;
