// clipYT Frontend Controller

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const urlInput = document.getElementById('video-url-input');
  const btnPaste = document.getElementById('btn-paste-url');
  const btnGenerate = document.getElementById('btn-generate-clips');
  const previewBox = document.getElementById('video-preview-box');
  const previewThumbnail = document.getElementById('preview-thumbnail');
  const previewTitle = document.getElementById('preview-title');
  const previewAuthor = document.getElementById('preview-author');
  const previewDuration = document.getElementById('preview-duration');

  const creatorCard = document.getElementById('creator-card');
  const processingCard = document.getElementById('processing-card');
  const progressBarFill = document.getElementById('progress-bar-fill');
  const statusTickerText = document.getElementById('status-ticker-text');
  const resultsSection = document.getElementById('results-section');
  const clipsGrid = document.getElementById('clips-grid-container');
  const btnNewClips = document.getElementById('btn-new-clips');

  // State
  let selectedAspect = 'portrait';
  let selectedFraming = 'fit_blur';
  let selectedSubtitleStyle = 'viral_yellow';
  let selectedClipCount = 3;
  let selectedMaxDuration = 45;
  let currentJobId = null;
  let eventSource = null;
  let previewDebounceTimer = null;

  // Initialize System Status
  checkSystemHealth();

  // Handle Option Clicks: Framing
  document.querySelectorAll('#framing-options .card-opt').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('#framing-options .card-opt').forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      selectedAspect = opt.dataset.aspect;
      selectedFraming = opt.dataset.framing;
    });
  });

  // Handle Option Clicks: Subtitle Style
  document.querySelectorAll('#subtitle-options .card-opt').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('#subtitle-options .card-opt').forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      selectedSubtitleStyle = opt.dataset.style;
    });
  });

  // Handle Pill Clicks: Clip Count
  document.querySelectorAll('#clip-count-group .pill-option').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#clip-count-group .pill-option').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      selectedClipCount = parseInt(pill.dataset.count);
    });
  });

  // Handle Pill Clicks: Max Duration
  document.querySelectorAll('#max-duration-group .pill-option').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#max-duration-group .pill-option').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      selectedMaxDuration = parseInt(pill.dataset.duration);
    });
  });

  // Paste from Clipboard
  btnPaste.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        fetchVideoPreview(urlInput.value);
        showToast('Pasted URL from clipboard');
      }
    } catch (e) {
      urlInput.focus();
    }
  });

  // URL Input listener with debounce for preview
  urlInput.addEventListener('input', () => {
    clearTimeout(previewDebounceTimer);
    const val = urlInput.value.trim();
    if (val.length > 10 && (val.includes('youtu.be') || val.includes('youtube.com'))) {
      previewDebounceTimer = setTimeout(() => fetchVideoPreview(val), 600);
    } else {
      previewBox.style.display = 'none';
    }
  });

  // Generate Clips CTA
  btnGenerate.addEventListener('click', async () => {
    const rawUrl = urlInput.value.trim();
    if (!rawUrl) {
      showToast('Please enter a YouTube video URL.');
      urlInput.focus();
      return;
    }

    btnGenerate.disabled = true;
    btnGenerate.innerHTML = '<span>⏳ Preparing Pipeline...</span>';

    try {
      const response = await fetch('/api/clip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_url: rawUrl,
          clip_count: selectedClipCount,
          max_duration: selectedMaxDuration,
          aspect_ratio: selectedAspect,
          framing_mode: selectedFraming,
          subtitle_style: selectedSubtitleStyle
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to start clipping job.');
      }

      const data = await response.json();
      currentJobId = data.job_id;

      // Show processing view
      creatorCard.style.display = 'none';
      resultsSection.style.display = 'none';
      processingCard.style.display = 'block';

      // Connect to SSE stream
      connectJobStream(currentJobId);

    } catch (err) {
      showToast('Error: ' + err.message);
      btnGenerate.disabled = false;
      btnGenerate.innerHTML = '<span>🚀 Generate Viral Clips</span>';
    }
  });

  // Reset to create more
  btnNewClips.addEventListener('click', () => {
    resultsSection.style.display = 'none';
    processingCard.style.display = 'none';
    creatorCard.style.display = 'block';
    btnGenerate.disabled = false;
    btnGenerate.innerHTML = '<span>🚀 Generate Viral Clips</span>';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Functions
  async function checkSystemHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        const geminiDot = document.getElementById('gemini-status-dot');
        const canaryDot = document.getElementById('canary-status-dot');
        const ffmpegDot = document.getElementById('ffmpeg-status-dot');

        if (data.tools.gemini_api_key_configured) {
          geminiDot.classList.remove('error');
          document.getElementById('gemini-status-text').textContent = 'Gemini Active';
        } else {
          geminiDot.classList.add('error');
          document.getElementById('gemini-status-text').textContent = 'Missing Gemini Key';
        }

        if (canaryDot) {
          if (data.tools.nvidia_canary_configured) {
            canaryDot.classList.remove('error');
            document.getElementById('canary-status-text').textContent = 'Canary ASR Ready';
          } else {
            canaryDot.classList.add('error');
            document.getElementById('canary-status-text').textContent = 'Canary Key Missing';
          }
        }

        if (data.tools.ffmpeg) {
          ffmpegDot.classList.remove('error');
          document.getElementById('ffmpeg-status-text').textContent = 'FFmpeg Ready';
        } else {
          ffmpegDot.classList.add('error');
          document.getElementById('ffmpeg-status-text').textContent = 'FFmpeg Missing';
        }
      }
    } catch (e) {
      console.warn('Health check failed', e);
    }
  }

  async function fetchVideoPreview(url) {
    try {
      const res = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_url: url })
      });
      const data = await res.json();
      if (data.ok && data.info) {
        previewThumbnail.src = data.info.thumbnail;
        previewTitle.textContent = data.info.title;
        previewAuthor.textContent = data.info.author;
        const mins = Math.floor(data.info.duration / 60);
        const secs = Math.floor(data.info.duration % 60);
        previewDuration.textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
        previewBox.style.display = 'flex';
      }
    } catch (e) {
      previewBox.style.display = 'none';
    }
  }

  function connectJobStream(jobId) {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/jobs/${jobId}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateProgressUI(data);

        if (data.status === 'completed') {
          eventSource.close();
          setTimeout(() => showResults(data.clips), 800);
        } else if (data.status === 'failed') {
          eventSource.close();
          showToast('Job failed: ' + (data.error || 'Unknown error'));
          btnGenerate.disabled = false;
          btnGenerate.innerHTML = '<span>🚀 Generate Viral Clips</span>';
          setTimeout(() => {
            processingCard.style.display = 'none';
            creatorCard.style.display = 'block';
          }, 3000);
        }
      } catch (e) {
        console.error('SSE parse error', e);
      }
    };

    eventSource.onerror = () => {
      console.warn('SSE stream closed or interrupted');
    };
  }

  function updateProgressUI(data) {
    const progress = Math.min(100, Math.max(0, data.progress || 0));
    progressBarFill.style.width = progress + '%';
    statusTickerText.textContent = data.step || 'Processing...';

    // Update Step indicators
    const step1 = document.getElementById('step-1');
    const step2 = document.getElementById('step-2');
    const step3 = document.getElementById('step-3');
    const step4 = document.getElementById('step-4');

    [step1, step2, step3, step4].forEach(s => s.classList.remove('active', 'completed'));

    if (progress >= 100) {
      [step1, step2, step3, step4].forEach(s => s.classList.add('completed'));
    } else if (progress >= 60) {
      step1.classList.add('completed');
      step2.classList.add('completed');
      step3.classList.add('completed');
      step4.classList.add('active');
    } else if (progress >= 50) {
      step1.classList.add('completed');
      step2.classList.add('completed');
      step3.classList.add('active');
    } else if (progress >= 20) {
      step1.classList.add('completed');
      step2.classList.add('active');
    } else {
      step1.classList.add('active');
    }
  }

  function showResults(clips) {
    processingCard.style.display = 'none';
    resultsSection.style.display = 'block';
    clipsGrid.innerHTML = '';

    if (!clips || clips.length === 0) {
      clipsGrid.innerHTML = '<p style="color: var(--text-muted); text-align: center; grid-column: 1/-1;">No clips were returned.</p>';
      return;
    }

    clips.forEach(clip => {
      const card = document.createElement('div');
      card.className = 'clip-card';
      
      const aspectClass = selectedAspect === 'landscape' ? 'style="aspect-ratio: 16/9; max-height: 280px;"' : '';

      card.innerHTML = `
        <div class="clip-video-box" ${aspectClass}>
          <video controls playsinline preload="metadata">
            <source src="${clip.video_url}" type="video/mp4">
            Your browser does not support video playback.
          </video>
          <div class="clip-score-badge">
            🔥 ${clip.score}/100
          </div>
          <div class="clip-duration-badge">
            ⏱️ ${clip.duration_seconds}s
          </div>
        </div>

        <div class="clip-body">
          <h4 class="clip-hook">${escapeHtml(clip.hook)}</h4>
          <div class="clip-caption-box">
            ${escapeHtml(clip.caption || 'No caption generated.')}
          </div>

          <div class="clip-actions">
            <button class="btn-action btn-copy-caption" title="Copy ready-to-post caption">
              📋 Caption
            </button>
            <button class="btn-action btn-copy-hook" title="Copy hook title">
              💡 Hook
            </button>
            <a href="${clip.download_url}" class="btn-action btn-download" download title="Download MP4 clip">
              ⬇ Download
            </a>
          </div>
        </div>
      `;

      // Copy buttons
      const btnCopyCaption = card.querySelector('.btn-copy-caption');
      btnCopyCaption.addEventListener('click', () => {
        navigator.clipboard.writeText(clip.caption || clip.hook);
        showToast('Caption & hashtags copied to clipboard!');
      });

      const btnCopyHook = card.querySelector('.btn-copy-hook');
      btnCopyHook.addEventListener('click', () => {
        navigator.clipboard.writeText(clip.hook);
        showToast('Hook title copied!');
      });

      clipsGrid.appendChild(card);
    });

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
  }

  function showToast(msg) {
    const toast = document.getElementById('toast-notification');
    toast.textContent = msg;
    toast.style.display = 'block';
    setTimeout(() => { toast.style.display = 'none'; }, 3200);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
