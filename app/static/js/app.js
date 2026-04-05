/* The Unified Theory of X — minimal JS for HTMX and UI interactions */

// Tab switching (used by review_drafts and episode pages)
function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(function(t) {
        t.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(function(b) {
        b.classList.remove('active');
    });
    var tab = document.getElementById('tab-' + name);
    if (tab) tab.classList.add('active');
    if (event && event.target) event.target.classList.add('active');
}

// Auto-refresh for tangent research status
document.addEventListener('DOMContentLoaded', function() {
    // If we're on a page with tangent research in progress, poll for updates
    var tangentStatus = document.querySelector('[data-tangent-poll]');
    if (tangentStatus) {
        var topicId = tangentStatus.dataset.topicId;
        setInterval(function() {
            window.location.reload();
        }, 5000);
    }
});
