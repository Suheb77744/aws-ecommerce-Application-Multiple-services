// session-watchdog.js
(function () {
    let idleTime = 0;
    const idleLimit = 15; // Log/Timeout after 15 minutes of dynamic passivity
    const API_URL = "http://YOUR_EC2_PUBLIC_IP:5000/api";
    const mockUserId = 1;

    // Reset timer on user interactions
    function resetTimer() {
        idleTime = 0;
    }

    window.onload = function() {
        window.onmousemove = resetTimer;
        window.onkeypress = resetTimer;
        
        // Increments every minute
        setInterval(async () => {
            idleTime++;
            if (idleTime >= idleLimit) {
                console.warn("User has gone idle. Logging status change.");
                try {
                    await fetch(`${API_URL}/activity`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_id: mockUserId,
                            service_name: 'session-watchdog',
                            activity_type: 'idle_timeout',
                            note: 'User became inactive for over 15 minutes.'
                        })
                    });
                } catch (e) {
                    console.error("Watchdog reporting failed", e);
                }
                resetTimer(); // Reset to avoid looping logs
            }
        }, 60000); 
    };
})();