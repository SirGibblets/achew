<script>
    import {chapterSearch} from '../../stores/chapterSearch.js';

    const TASK_LABELS = {
        'sync': 'Syncing library…',
        'search': 'Searching…',
    };

    $: task = $chapterSearch.currentTask;
    $: label = TASK_LABELS[task] || 'Working…';
    $: progress = $chapterSearch.progress || {current: 0, total: 0};
    $: percent = progress.total > 0
        ? Math.round((progress.current / progress.total) * 100)
        : 0;
    $: progressText = progress.total > 0
        ? `${progress.current} / ${progress.total}`
        : '';
</script>

<div class="searching-page">
    <h3 class="task-label">{label}</h3>

    <div class="progress-wrap">
        <div class="progress-header">
            <span class="progress-text">{progressText}</span>
            <span class="progress-pct">{percent}%</span>
        </div>
        <div class="progress-track">
            <div class="progress-bar" style="width: {percent}%"></div>
        </div>
    </div>

    <button class="btn btn-cancel" on:click={() => chapterSearch.cancel()}>
        Cancel
    </button>
</div>

<style>
    .searching-page {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1.5rem;
        padding: 2rem 1rem;
        width: 100%;
        max-width: 480px;
        margin: 0 auto;
    }

    .task-label {
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--text-primary);
        margin: 0;
    }

    .progress-wrap {
        width: 100%;
    }

    .progress-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 0.5rem;
        font-size: 0.875rem;
        color: var(--text-secondary);
    }

    .progress-pct {
        font-weight: 600;
        color: var(--primary);
    }

    .progress-track {
        height: 0.5rem;
        background: var(--bg-tertiary);
        border-radius: 0.75rem;
        overflow: hidden;
    }

    .progress-bar {
        height: 100%;
        background: var(--primary);
        border-radius: 0.75rem;
        transition: width 0.2s ease;
    }

    .btn-cancel {
        margin-top: 0.5rem;
    }
</style>
