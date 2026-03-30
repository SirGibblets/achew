<script>
    import ArrowLeft from "@lucide/svelte/icons/arrow-left";
    import { chapterSearch } from "../../stores/chapterSearch.js";

    $: stats = $chapterSearch.stats;
    $: libraryName = $chapterSearch.libraryName;

    function formatNumber(num, decimals = 0) {
        if (num == null) return "—";
        return Number(num).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    function formatJob(job) {
        if (!job) return "—";
        if (job.value != null && job.unit) {
            return `${formatNumber(job.value, 1)} ${job.unit}`;
        }
        return job.display || "—";
    }

    function formatDuration(seconds) {
        if (!seconds || seconds < 0) return "0s";
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) return `${formatNumber(h)}h ${m}m`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function coverUrl(item) {
        const id = item.book_id || item.id;
        if (!item.has_cover || !id) return null;
        return `/api/audiobookshelf/covers/${id}`;
    }

    function absLink(item) {
        const id = item.book_id || item.id;
        if (!stats?.abs_url || !id) return null;
        return `${stats.abs_url}/audiobookshelf/item/${id}`;
    }
</script>

<div class="stats-page">
    <!-- Top bar -->
    <div class="top-bar">
        <button class="back-btn" on:click={() => chapterSearch.backToLanding()}>
            <ArrowLeft size="16" /> Back
        </button>
    </div>

    {#if stats}
        <div class="stats-content">
            <div class="page-header">
                {#if libraryName}
                    <h2 class="main-title">{libraryName}</h2>
                    <h3 class="sub-title">Library Stats</h3>
                {:else}
                    <h2 class="main-title">Library Stats</h2>
                {/if}
            </div>

            <div class="top-stats-container">
                <!-- Top Stats (3-column grid) -->
                <div class="stat-cards top-stats">
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatNumber(stats.total_books)}
                        </div>
                        <div class="stat-label">Books in library</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatNumber(stats.total_chapters)}
                        </div>
                        <div class="stat-label">Total chapters</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatNumber(stats.avg_chapters, 1)}
                        </div>
                        <div class="stat-label">Avg chapters per book</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatDuration(stats.total_library_seconds)}
                        </div>
                        <div class="stat-label">Total library duration</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatDuration(stats.avg_book_length_seconds)}
                        </div>
                        <div class="stat-label">Avg book duration</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">
                            {formatDuration(stats.avg_chapter_length_seconds)}
                        </div>
                        <div class="stat-label">Avg chapter duration</div>
                    </div>
                </div>

                <div class="stat-card highlight">
                    <div class="stat-value">
                        {formatJob(stats.full_time_job)}
                    </div>
                    <div class="stat-label">
                        How long it would take to listen<br />to the entire
                        library as a full-time job
                    </div>
                </div>
            </div>

            <!-- Book Stats Grid (2-column) -->
            <div class="book-stats-grid">
                {#if stats.most_chapters_book}
                    <div class="book-stat">
                        <span class="book-stat-label">Most Chapters</span>
                        <a
                            class="book-ref"
                            href={absLink(stats.most_chapters_book)}
                            target="_blank"
                            rel="noopener"
                        >
                            <div class="book-cover">
                                {#if coverUrl(stats.most_chapters_book)}
                                    <img
                                        src={coverUrl(stats.most_chapters_book)}
                                        alt=""
                                        loading="lazy"
                                    />
                                {:else}
                                    <div class="cover-placeholder"></div>
                                {/if}
                            </div>
                            <div class="book-ref-info">
                                <span class="book-ref-title"
                                    >{stats.most_chapters_book.name}</span
                                >
                                <span class="book-ref-detail"
                                    >{formatNumber(
                                        stats.most_chapters_book.chapter_count,
                                    )} chapters</span
                                >
                            </div>
                        </a>
                    </div>
                {/if}

                {#if stats.longest_chapter}
                    <div class="book-stat">
                        <span class="book-stat-label">Longest Chapter</span>
                        <a
                            class="book-ref"
                            href={absLink(stats.longest_chapter)}
                            target="_blank"
                            rel="noopener"
                        >
                            <div class="book-cover">
                                {#if coverUrl(stats.longest_chapter)}
                                    <img
                                        src={coverUrl(stats.longest_chapter)}
                                        alt=""
                                        loading="lazy"
                                    />
                                {:else}
                                    <div class="cover-placeholder"></div>
                                {/if}
                            </div>
                            <div class="book-ref-info">
                                <span class="book-ref-title"
                                    >{stats.longest_chapter.book_name}</span
                                >
                                <span class="book-ref-detail"
                                    >"{stats.longest_chapter.title}" — {formatDuration(
                                        stats.longest_chapter.duration_seconds,
                                    )}</span
                                >
                            </div>
                        </a>
                    </div>
                {/if}

                {#if stats.longest_book}
                    <div class="book-stat">
                        <span class="book-stat-label">Longest Book</span>
                        <a
                            class="book-ref"
                            href={absLink(stats.longest_book)}
                            target="_blank"
                            rel="noopener"
                        >
                            <div class="book-cover">
                                {#if coverUrl(stats.longest_book)}
                                    <img
                                        src={coverUrl(stats.longest_book)}
                                        alt=""
                                        loading="lazy"
                                    />
                                {:else}
                                    <div class="cover-placeholder"></div>
                                {/if}
                            </div>
                            <div class="book-ref-info">
                                <span class="book-ref-title"
                                    >{stats.longest_book.name}</span
                                >
                                <span class="book-ref-detail"
                                    >{formatDuration(
                                        stats.longest_book.duration_seconds,
                                    )}</span
                                >
                            </div>
                        </a>
                    </div>
                {/if}

                {#if stats.shortest_book}
                    <div class="book-stat">
                        <span class="book-stat-label">Shortest Book</span>
                        <a
                            class="book-ref"
                            href={absLink(stats.shortest_book)}
                            target="_blank"
                            rel="noopener"
                        >
                            <div class="book-cover">
                                {#if coverUrl(stats.shortest_book)}
                                    <img
                                        src={coverUrl(stats.shortest_book)}
                                        alt=""
                                        loading="lazy"
                                    />
                                {:else}
                                    <div class="cover-placeholder"></div>
                                {/if}
                            </div>
                            <div class="book-ref-info">
                                <span class="book-ref-title"
                                    >{stats.shortest_book.name}</span
                                >
                                <span class="book-ref-detail"
                                    >{formatDuration(
                                        stats.shortest_book.duration_seconds,
                                    )}</span
                                >
                            </div>
                        </a>
                    </div>
                {/if}
            </div>

            <!-- Full Width Stats -->
            {#if stats.longest_chapter_title}
                <div class="book-stat">
                    <span class="book-stat-label">Longest Chapter Title</span>
                    <a
                        class="book-ref"
                        href={absLink(stats.longest_chapter_title)}
                        target="_blank"
                        rel="noopener"
                    >
                        <div class="book-cover">
                            {#if coverUrl(stats.longest_chapter_title)}
                                <img
                                    src={coverUrl(stats.longest_chapter_title)}
                                    alt=""
                                    loading="lazy"
                                />
                            {:else}
                                <div class="cover-placeholder"></div>
                            {/if}
                        </div>
                        <div class="book-ref-info">
                            <span class="book-ref-title"
                                >{stats.longest_chapter_title.book_name}</span
                            >
                            <span class="book-ref-detail chapter-name"
                                >"{stats.longest_chapter_title.title}"</span
                            >
                        </div>
                    </a>
                </div>
            {/if}

            {#if stats.most_common_words && stats.most_common_words.length > 0}
                <div class="book-stat">
                    <span class="book-stat-label"
                        >Most Common Words in Chapter Titles</span
                    >
                    <span class="book-stat-sublabel"
                        >Excludes numbers and common words like "chapter",
                        "and", "to", etc.</span
                    >
                    <div class="word-list">
                        {#each stats.most_common_words as { word, count }}
                            <span class="word-badge">
                                <span class="word-text">{word}</span>
                                <span class="word-count">{formatNumber(count)}</span>
                            </span>
                        {/each}
                    </div>
                </div>
            {/if}
        </div>
    {:else}
        <div class="empty-state">No stats available.</div>
    {/if}
</div>

<style>
    .stats-page {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        width: 100%;
        height: 100%;
    }

    .top-bar {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .back-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.875rem;
        cursor: pointer;
        flex-shrink: 0;
    }
    .back-btn:hover {
        color: var(--text-primary);
    }

    .page-header {
        display: flex;
        flex-direction: column;
        align-items: center;
        margin-bottom: 0.5rem;
    }

    .main-title {
        font-size: 2rem;
        font-weight: 700;
        color: var(--text-primary);
        margin: 0;
    }

    .sub-title {
        font-size: 0.85rem;
        font-weight: 400;
        color: var(--text-secondary);
        margin: 0;
    }

    .stats-content {
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
        overflow-y: auto;
        padding-bottom: 1rem;
    }

    .top-stats-container {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .stat-cards {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.5rem;
    }

    .book-stats-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.75rem;
        margin-bottom: -0.75rem;
    }

    .stat-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 0.75rem 0.5rem;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        text-align: center;
    }

    .stat-card.highlight {
        flex-direction: row;
        justify-content: center;
        gap: 0.75rem;
        border-color: color-mix(in srgb, var(--primary-color) 50%, transparent);
        background: color-mix(in srgb, var(--primary) 8%, var(--bg-secondary));
    }

    .stat-card.highlight .stat-value {
        font-size: 1.75rem;
        font-weight: 600;
    }

    .stat-card.highlight .stat-label {
        text-align: left;
        font-size: 0.7rem;
        line-height: 1.2;
        margin-top: 0.05rem;
    }

    .stat-value {
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .stat-label {
        font-size: 0.75rem;
        color: var(--text-secondary);
    }

    .book-stat {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
    }

    .book-stat-label {
        font-size: 0.8125rem;
        font-weight: 500;
        color: var(--text-secondary);
    }

    .book-stat-sublabel {
        font-size: 0.7rem;
        color: var(--text-secondary);
        opacity: 0.8;
        line-height: 1.2;
        margin-top: -0.25rem;
        margin-bottom: 0.4rem;
    }

    .book-ref {
        display: flex;
        align-items: center;
        gap: 0.625rem;
        padding: 0.5rem 0.625rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        text-decoration: none;
        color: inherit;
        transition:
            background 0.1s,
            border-color 0.1s;
    }
    .book-ref:hover {
        background: var(--bg-secondary);
        border-color: var(--primary);
    }

    .book-cover {
        width: 40px;
        height: 40px;
        flex-shrink: 0;
        border-radius: 4px;
        overflow: hidden;
    }

    .book-cover img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }

    .cover-placeholder {
        width: 100%;
        height: 100%;
        background: var(--bg-tertiary);
    }

    .book-ref-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 0.1rem;
    }

    .book-ref-title {
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .book-ref-detail {
        font-size: 0.75rem;
        color: var(--text-secondary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .book-ref-detail.chapter-name {
        white-space: normal;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }

    .word-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.375rem;
    }

    .word-badge {
        display: inline-flex;
        align-items: stretch;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 999px;
        font-size: 0.8125rem;
        color: var(--text-primary);
        overflow: hidden;
    }

    .word-text {
        padding: 0.25rem 0.1rem 0.25rem 0.75rem;
    }

    .word-count {
        font-size: 0.625rem;
        color: var(--text-secondary);
        background: var(--bg-tertiary);
        padding: 0 0.375rem 0 0.325rem;
        margin-left: 0.375rem;
        display: flex;
        align-items: center;
    }

    .empty-state {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 1;
        padding: 2rem;
        color: var(--text-secondary);
        font-size: 0.9rem;
    }
</style>
