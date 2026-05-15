document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('shorten-form');
    const urlInput = document.getElementById('url-input');
    const resultArea = document.getElementById('result-area');
    const shortUrlAnchor = document.getElementById('short-url');
    const copyBtn = document.getElementById('copy-btn');
    const recentList = document.getElementById('recent-list');
    const submitBtn = document.getElementById('submit-btn');

    // Load recent URLs on page load
    loadRecentUrls();

    // ── Form Submission ──────────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const longUrl = urlInput.value;
        
        // Disable button and show loading state
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Shortening...';

        try {
            const response = await fetch('/api/shorten', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: longUrl }),
            });

            if (!response.ok) {
                throw new Error('Failed to shorten URL');
            }

            const data = await response.json();
            
            // Show result
            shortUrlAnchor.href = data.short_url;
            shortUrlAnchor.textContent = data.short_url;
            resultArea.classList.add('visible');
            
            // Clear input
            urlInput.value = '';
            
            // Reload recent URLs
            loadRecentUrls();
            
        } catch (error) {
            alert('Error: ' + error.message);
        } finally {
            // Restore button state
            submitBtn.disabled = false;
            submitBtn.innerHTML = `Shorten <i data-lucide="arrow-right" style="margin-left: 0.5rem; width: 18px;"></i>`;
            lucide.createIcons(); // Re-initialize icons since we innerHTML'd
        }
    });

    // ── Copy to Clipboard ────────────────────────────────────────
    copyBtn.addEventListener('click', () => {
        const textToCopy = shortUrlAnchor.textContent;
        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast();
        }).catch(err => {
            console.error('Failed to copy: ', err);
        });
    });

    // ── Load Recent URLs ─────────────────────────────────────────
    async function loadRecentUrls() {
        try {
            const response = await fetch('/api/recent');
            if (!response.ok) throw new Error('Failed to load');
            
            const urls = await response.json();
            
            if (urls.length === 0) {
                recentList.innerHTML = `<li class="recent-item" style="color: var(--text-secondary); justify-content: center;">No links created yet.</li>`;
                return;
            }

            recentList.innerHTML = urls.map(url => `
                <li class="recent-item">
                    <div class="recent-urls">
                        <a href="${url.short_url}" class="recent-short" target="_blank">${url.short_url}</a>
                        <span class="recent-original" title="${url.original_url}">${url.original_url}</span>
                    </div>
                    <div class="recent-clicks" title="Total clicks">${url.click_count} clicks</div>
                </li>
            `).join('');

        } catch (error) {
            recentList.innerHTML = `<li class="recent-item" style="color: var(--text-secondary); justify-content: center;">Failed to load recent links.</li>`;
            console.error(error);
        }
    }

    // ── Toast Notification ───────────────────────────────────────
    function showToast() {
        const toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 2000);
    }
});
